"""Document Parser Engine — auto-detect document type and route to correct OCR pipeline.

Routes documents through the pipeline based on detected type:

  ┌─────────┐   ┌──────────┐   ┌──────────────┐
  │ Typed   │ → │ Docling  │ → │ Structured   │
  │ PDF     │   │          │   │ JSON         │
  ├─────────┤   ├──────────┤   ├──────────────┤
  │ Scanned │ → │ Surya    │ → │ Docling      │
  │ PDF     │   │ layout   │   │ structure    │
  ├─────────┤   ├──────────┤   ├──────────────┤
  │ Hand-   │ → │ Nanonets-│ → │ MedGemma     │
  │ written │   │ OCR2     │   │ fallback     │
  ├─────────┤   ├──────────┤   ├──────────────┤
  │ Photo   │ → │ Surya    │ → │ MedGemma     │
  │ (jpg)   │   │          │   │ re-check     │
  └─────────┘   └──────────┘   └──────────────┘
                    ↓
           ┌──────────────────┐
           │ Parser Router    │
           │ → structured doc │
           │ → version draft  │
           └──────────────────┘

Usage:
    from app.services.document_parser import DocumentParser
    parser = DocumentParser()
    result = await parser.parse_document(file_path="...", mime_type="application/pdf")
    # -> {"doc_type": "prescription", "structured": {...}, "confidence": 0.92}
"""

from __future__ import annotations

import os
import re
import json
import logging
import magic
from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Schema Aligner (Feature D) ───
# Lazy import to avoid circular dependency
_schema_aligner = None


def _get_schema_aligner():
    """Get or create SchemaAligner instance for Feature D zero-shot alignment."""
    global _schema_aligner
    if _schema_aligner is None:
        try:
            from app.services.schema_aligner import SchemaAligner
            _schema_aligner = SchemaAligner()
            logger.info("SchemaAligner (Feature D) initialized for document parsing")
        except Exception as exc:
            logger.warning("Could not initialize SchemaAligner: %s", exc)
            return None
    return _schema_aligner

# ─── Document Types ─────────────────────────────────

class DocType(str, Enum):
    PRESCRIPTION = "prescription"
    LAB_REPORT = "lab_report"
    DISCHARGE_SUMMARY = "discharge_summary"
    REFERRAL_LETTER = "referral_letter"
    IMAGING_REPORT = "imaging_report"
    GENERAL_DOCUMENT = "general_document"

class DocFormat(str, Enum):
    TYPED_PDF = "typed_pdf"
    SCANNED_PDF = "scanned_pdf"
    HANDWRITTEN = "handwritten"
    PHOTO = "photo"
    UNKNOWN = "unknown"


# ─── Parser Router ──────────────────────────────────

class ParserRouter:
    """Auto-detect document format and route to correct parser."""

    def __init__(self):
        self._ocr_service = OCRService()

    async def detect_format(self, file_path: str, mime_type: str) -> Tuple[DocFormat, float]:
        """Detect document format using MIME type + content analysis.

        Returns:
            (format, confidence)
        """
        # MIME-based detection
        if mime_type == "application/pdf":
            # Determine if scanned or typed by checking for text layer
            has_text = await self._check_pdf_has_text(file_path)
            if has_text:
                return DocFormat.TYPED_PDF, 0.9
            else:
                return DocFormat.SCANNED_PDF, 0.8

        elif mime_type.startswith("image/"):
            # Check image characteristics for handwriting vs printed
            is_handwritten = await self._detect_handwriting(file_path)
            if is_handwritten:
                return DocFormat.HANDWRITTEN, 0.7
            return DocFormat.PHOTO, 0.8

        return DocFormat.UNKNOWN, 0.0

    async def parse(self, file_path: str, mime_type: str) -> Dict[str, Any]:
        """Parse a document through the full pipeline.

        1. Detect format
        2. Route to correct OCR / parser
        3. Extract structured content
        4. Classify document type
        5. Return structured result

        Args:
            file_path: Path to the uploaded document.
            mime_type: MIME type of the document.

        Returns:
            {
                "status": "ok" | "error",
                "doc_type": "prescription" | ...,
                "doc_format": "typed_pdf" | ...,
                "raw_text": str,
                "structured": {...},
                "confidence": 0.0-1.0,
                "took_ms": float,
            }
        """
        start = datetime.now(timezone.utc)

        if not os.path.exists(file_path):
            return {"status": "error", "message": f"File not found: {file_path}"}

        # Step 1: Detect format
        doc_format, format_confidence = await self.detect_format(file_path, mime_type)
        logger.info("Detected format: %s (confidence=%.2f)", doc_format, format_confidence)

        # Step 1b: Image quality checks (blur, contrast, brightness)
        quality_warnings: list[str] = []
        if mime_type.startswith("image/"):
            quality_warnings = await self._check_image_quality(file_path)
            if quality_warnings:
                logger.info("Image quality warnings: %s", quality_warnings)

        # Step 2: Extract text via correct pipeline
        raw_text = ""
        extraction_confidence = 0.0

        if doc_format == DocFormat.TYPED_PDF:
            raw_text, extraction_confidence = await self._parse_typed_pdf(file_path)
        elif doc_format == DocFormat.SCANNED_PDF:
            raw_text, extraction_confidence = await self._parse_scanned_pdf(file_path)
        elif doc_format == DocFormat.HANDWRITTEN:
            raw_text, extraction_confidence = await self._parse_handwritten(file_path)
        elif doc_format == DocFormat.PHOTO:
            raw_text, extraction_confidence = await self._parse_photo(file_path)
        else:
            # Fallback: try all
            raw_text, extraction_confidence = await self._parse_unknown(file_path)

        if not raw_text.strip():
            return {
                "status": "error",
                "message": "No text could be extracted from the document",
                "doc_format": doc_format.value,
                "doc_type": DocType.GENERAL_DOCUMENT.value,
                "raw_text": "",
                "structured": {},
                "confidence": 0.0,
                "quality_warnings": quality_warnings,
            }

        # Step 3: Classify document type from content
        doc_type, type_confidence = self._classify_document_type(raw_text)

        # Step 4: Build structured output
        structured = await self._build_structured(raw_text, doc_type)

        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        logger.info(
            "Document parsed: type=%s format=%s text_len=%d confidence=%.2f took=%.0fms",
            doc_type.value, doc_format.value, len(raw_text), extraction_confidence, elapsed,
        )

        return {
            "status": "ok",
            "doc_type": doc_type.value,
            "doc_format": doc_format.value,
            "raw_text": raw_text,
            "structured": structured,
            "confidence": round(extraction_confidence, 3),
            "took_ms": round(elapsed, 1),
            "quality_warnings": quality_warnings,
        }

    # ─── Format Detection Helpers ───

    async def _check_pdf_has_text(self, file_path: str) -> bool:
        """Check if a PDF has extractable text layer (vs scanned image)."""
        try:
            import PyPDF2
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages[:3]:
                    text = page.extract_text() or ""
                    if len(text.strip()) > 50:
                        return True
            return False
        except ImportError:
            # Fallback: check file size (typed PDFs with text are usually smaller)
            size = os.path.getsize(file_path)
            return size < 500_000  # heuristic
        except Exception as exc:
            logger.warning("PDF text check failed: %s", exc)
            return False

    async def _detect_handwriting(self, file_path: str) -> bool:
        """Detect if image contains handwriting vs printed text.

        Heuristic: check file name patterns and basic image properties.
        Full detection requires an ML model (deferred to Week 9).
        """
        # Heuristic: check if filename contains "rx", "presc", "hand"
        basename = os.path.basename(file_path).lower()
        handwriting_indicators = ["rx", "presc", "hand", "note", "scrip"]
        for indicator in handwriting_indicators:
            if indicator in basename:
                return True
        return False

    async def _check_image_quality(self, file_path: str) -> list[str]:
        """Analyze image quality and return warning messages.

        Checks: blur (Laplacian variance), low contrast, dark/underexposed.
        Returns a list of human-readable warning strings (empty = all good).
        """
        try:
            from PIL import Image
            import numpy as np
        except ImportError:
            return []

        try:
            img = Image.open(file_path)
        except Exception:
            return []

        warnings = []
        img_array = np.array(img.convert("L"))  # grayscale

        # ── Blur check (Laplacian variance) ──
        # Low variance = blurry image
        laplacian_var = float(np.var(np.diff(img_array.astype(np.float64), axis=0)))
        if laplacian_var < 100:
            warnings.append("Image appears blurry — retake for better accuracy")
        elif laplacian_var < 300:
            warnings.append("Image may be slightly blurry — verify extracted text")

        # ── Contrast check (std deviation of pixel intensities) ──
        contrast = float(np.std(img_array))
        if contrast < 20:
            warnings.append("Low contrast — text may be hard to read")
        elif contrast < 35:
            warnings.append("Low contrast detected — some text may be missed")

        # ── Brightness check (mean pixel intensity) ──
        mean_brightness = float(np.mean(img_array))
        if mean_brightness < 50:
            warnings.append("Image appears dark/underexposed")
        elif mean_brightness > 230:
            warnings.append("Image appears overexposed / washed out")

        # ── Resolution check ──
        width, height = img.size
        if width < 500 or height < 500:
            warnings.append(f"Low resolution ({width}x{height}) — larger images improve OCR")

        return warnings

    # ─── OCR Pipeline Methods ───

    async def _parse_typed_pdf(self, file_path: str) -> Tuple[str, float]:
        """Parse typed PDF using Docling."""
        text, confidence = await self._ocr_service.docling_parse(file_path)
        return text, confidence

    async def _parse_scanned_pdf(self, file_path: str) -> Tuple[str, float]:
        """Parse scanned PDF: Surya layout -> Docling structure."""
        text, confidence = await self._ocr_service.surya_parse(file_path)
        return text, confidence

    async def _parse_handwritten(self, file_path: str) -> Tuple[str, float]:
        """Parse handwritten document: Nanonets-OCR2-1.5B-exp -> MedGemma fallback."""
        text, confidence = await self._ocr_service.nanonnets_ocr_parse(file_path)
        if not text.strip() or confidence < 0.3:
            # Fallback to MedGemma
            text2, conf2 = await self._ocr_service.medgemma_parse(file_path)
            if len(text2) > len(text):
                return text2, conf2
        return text, confidence

    async def _parse_photo(self, file_path: str) -> Tuple[str, float]:
        """Parse photo: Surya -> MedGemma re-check."""
        text, confidence = await self._ocr_service.surya_parse(file_path)
        if confidence < 0.5:
            text2, conf2 = await self._ocr_service.medgemma_parse(file_path)
            if len(text2) > len(text):
                return text2, conf2
        return text, confidence

    async def _parse_unknown(self, file_path: str) -> Tuple[str, float]:
        """Try all parsers in order, return best result using weighted scoring."""
        best_text = ""
        best_score = 0.0
        best_conf = 0.0

        for parser_name in ["docling_parse", "surya_parse", "nanonets_ocr_parse", "medgemma_parse"]:
            try:
                parser_fn = getattr(self._ocr_service, parser_name)
                text, conf = await parser_fn(file_path)
                # Weighted score: longer text with decent confidence beats short text with high confidence
                score = len(text) * conf
                if score > best_score:
                    best_text = text
                    best_score = score
                    best_conf = conf
            except Exception:
                continue

        return best_text, best_conf

    # ─── Document Type Classification ───

    DOC_TYPE_PATTERNS: Dict[DocType, List[str]] = {
        DocType.PRESCRIPTION: [
            r"(?i)(prescription|rx|take|medication|tab|capsule|syrup|dose|mg|mcg|bd|od|tid|hs)",
        ],
        DocType.LAB_REPORT: [
            r"(?i)(lab|report|test|result|hb|wbc|rbc|hba1c|cholesterol|glucose|creatinine|sodium|potassium)",
        ],
        DocType.DISCHARGE_SUMMARY: [
            r"(?i)(discharge|admission|hospital|stay|condition at discharge|follow.?up)",
        ],
        DocType.REFERRAL_LETTER: [
            r"(?i)(referral|referred|dear doctor|consultation|specialist|opinion)",
        ],
        DocType.IMAGING_REPORT: [
            r"(?i)(x.?ray|ct|mri|ultrasound|sonography|echocardiography|imaging|scan|radiologist)",
        ],
    }

    def _classify_document_type(self, text: str) -> Tuple[DocType, float]:
        """Classify document type from extracted text content."""
        text_lower = text.lower()
        scores = {}

        for doc_type, patterns in self.DOC_TYPE_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, text)
                score += len(matches)
            scores[doc_type] = score

        if not scores or max(scores.values()) == 0:
            return DocType.GENERAL_DOCUMENT, 0.0

        best_type = max(scores, key=scores.get)
        total = sum(scores.values())
        confidence = min(scores[best_type] / max(total, 1), 1.0)

        return best_type, round(confidence, 3)

    # ─── Structured Output Builder ───

    async def _build_structured(self, text: str, doc_type: DocType) -> Dict[str, Any]:
        """Build structured representation from raw text.

        Tries Feature D (SchemaAligner) first for canonical Pydantic schema.
        Falls back to regex-based extraction if SchemaAligner unavailable or fails.
        """
        # Try Feature D: Zero-shot schema alignment
        aligner = _get_schema_aligner()
        if aligner and doc_type != DocType.GENERAL_DOCUMENT:
            try:
                result = await aligner.align(raw_text=text, doc_type=doc_type.value)
                if result.get("status") == "ok" and result.get("structured"):
                    structured = result["structured"]
                    structured["_aligned_by"] = "schema_aligner_feature_d"
                    structured["_alignment_confidence"] = result.get("confidence", 0.0)
                    structured["_validation_status"] = result.get("validation", "unknown")
                    return structured
            except Exception as exc:
                logger.warning("SchemaAligner failed for %s: %s, falling back to regex", doc_type, exc)

        # Fallback: basic regex-based extraction (original behavior)
        result = {
            "type": doc_type.value,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "text_length": len(text),
        }

        # Extract date patterns
        date_patterns = [
            r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}",
        ]
        dates_found = []
        for pattern in date_patterns:
            dates_found.extend(re.findall(pattern, text))
        if dates_found:
            result["dates_mentioned"] = list(set(dates_found))

        # Extract potential medication names (for prescriptions)
        if doc_type == DocType.PRESCRIPTION:
            med_pattern = r"(?i)([A-Z][a-z]+(?:cin|mide|pril|sartan|lol|pine|pam|done|zole|vir|bicin|mycin|micin))\b"
            meds = list(set(re.findall(med_pattern, text)))
            if meds:
                result["medications_found"] = meds

        # Extract potential numeric values (lab values)
        if doc_type == DocType.LAB_REPORT:
            num_pattern = r"(\d+\.?\d*)\s*(mg/dL|g/dL|mEq/L|U/L|mmol/L|%|cells/mm3)"
            values = re.findall(num_pattern, text)
            if values:
                result["numeric_values"] = [{"value": v, "unit": u} for v, u in values[:20]]

        return result


# ─── OCR Service ─────────────────────────────────────

class OCRService:
    """Unified OCR service wrapping document parsing libraries.

    Each method returns (text: str, confidence: float).
    Methods are designed to work with the libraries when installed,
    and provide meaningful fallback text when they aren't.
    """

    async def docling_parse(self, file_path: str) -> Tuple[str, float]:
        """Parse a typed PDF using Docling (IBM).

        Falls back to PyPDF2 or pdfminer if Docling isn't installed.
        """
        try:
            from docling.document_converter import DocumentConverter
            converter = DocumentConverter()
            result = converter.convert(file_path)
            text = result.document.export_to_markdown()
            if text.strip():
                return text, 0.95
        except ImportError:
            logger.info("Docling not installed, falling back to PyPDF2")
            return await self._pypdf2_fallback(file_path)
        except Exception as exc:
            logger.warning("Docling parsing failed: %s, falling back", exc)
            return await self._pypdf2_fallback(file_path)
        return "", 0.0

    async def surya_parse(self, file_path: str) -> Tuple[str, float]:
        """Parse a scanned document using Surya OCR.

        Falls back to pytesseract if Surya isn't installed.
        """
        try:
            from surya.ocr import run_ocr
            from PIL import Image
            image = Image.open(file_path)
            text_lines = run_ocr(image, [{"lang": "en"}])
            lines = []
            for line in text_lines:
                if hasattr(line, 'text'):
                    lines.append(line.text)
                elif isinstance(line, dict):
                    lines.append(line.get('text', ''))
            text = "\n".join(lines)
            if text.strip():
                return text, 0.85
        except ImportError:
            logger.info("Surya not installed, falling back to Tesseract")
            return await self._tesseract_fallback(file_path)
        except Exception as exc:
            logger.warning("Surya parsing failed: %s, falling back", exc)
            return await self._tesseract_fallback(file_path)
        return "", 0.0

    async def nanonets_ocr_parse(self, file_path: str) -> Tuple[str, float]:
        """Parse handwritten/printed text using Nanonets-OCR2-1.5B-exp.

        This is a SOTA open-source OCR model (Apache 2.0) that handles:
        - Handwritten text
        - Printed text
        - Tables and forms
        - Multiple languages

        Falls back to Tesseract if Nanonets-OCR isn't available.
        """
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from PIL import Image
            import torch

            model_name = settings.NANONETS_OCR_MODEL

            # Cache model and tokenizer
            if not hasattr(self, "_nanonets_model") or self._nanonets_model is None:
                logger.info("Loading Nanonets-OCR2-1.5B model...")
                self._nanonets_tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
                self._nanonets_model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                    device_map="auto" if torch.cuda.is_available() else None,
                    trust_remote_code=True,
                )
                logger.info("Nanonets-OCR2 loaded successfully")

            tokenizer = self._nanonets_tokenizer
            model = self._nanonets_model

            with Image.open(file_path) as image:
                if image.mode != "RGB":
                    image = image.convert("RGB")
                prompt = "Extract all text from this document."
                inputs = tokenizer(prompt, images=image, return_tensors="pt").to(model.device)
                outputs = model.generate(**inputs, max_new_tokens=1024, do_sample=False)
                text = tokenizer.decode(outputs[0], skip_special_tokens=True)
                if text.strip():
                    return text, 0.90  # High confidence for SOTA model
        except ImportError:
            logger.info("Nanonets-OCR not installed, falling back to Tesseract")
            return await self._tesseract_fallback(file_path, psm=13)
        except Exception as exc:
            logger.warning("Nanonets-OCR parsing failed: %s, falling back", exc)
            return await self._tesseract_fallback(file_path)
        return "", 0.0

    async def got_ocr_parse(self, file_path: str) -> Tuple[str, float]:
        """Parse handwritten text using GOT-OCR 2.0 (DEPRECATED - kept for fallback).

        Falls back to Tesseract with handwriting config if GOT-OCR isn't installed.
        """
        logger.warning("GOT-OCR 2.0 is deprecated; use Nanonets-OCR2-1.5B-exp instead")
        try:
            from got_ocr import GOTOCR
            model = GOTOCR()
            text = model.infer(file_path)
            if text.strip():
                return text, 0.80
        except ImportError:
            logger.info("GOT-OCR not installed, falling back to Tesseract hand-print")
            return await self._tesseract_fallback(file_path, psm=13)
        except Exception as exc:
            logger.warning("GOT-OCR parsing failed: %s, falling back", exc)
            return await self._tesseract_fallback(file_path)
        return "", 0.0

    async def medgemma_parse(self, file_path: str) -> Tuple[str, float]:
        """Parse image using MedGemma-4B local VLM as fallback.

        Falls back to basic Tesseract if MedGemma isn't loaded.
        Model is cached after first load to avoid reloading on every call.
        """
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from PIL import Image

            model_name = settings.MEDGEMMA_PATH or "/models/medgemma-4b-it"

            # Cache model and tokenizer to avoid reloading on every call
            if not hasattr(self, "_medgemma_model") or self._medgemma_model is None:
                self._medgemma_tokenizer = AutoTokenizer.from_pretrained(model_name)
                self._medgemma_model = AutoModelForCausalLM.from_pretrained(model_name)

            tokenizer = self._medgemma_tokenizer
            model = self._medgemma_model

            # Open image and pass to VLM (was previously ignored)
            with Image.open(file_path) as image:
                prompt = "Extract all text from this medical document."
                inputs = tokenizer(prompt, images=image, return_tensors="pt")
                outputs = model.generate(**inputs, max_new_tokens=512)
                text = tokenizer.decode(outputs[0], skip_special_tokens=True)
                if text.strip():
                    return text, 0.75
        except ImportError:
            logger.info("MedGemma not available, falling back to Tesseract")
            return await self._tesseract_fallback(file_path)
        except Exception as exc:
            logger.warning("MedGemma parsing failed: %s, falling back", exc)
            return await self._tesseract_fallback(file_path)
        return "", 0.0

    # ─── Fallbacks ───

    async def _pypdf2_fallback(self, file_path: str) -> Tuple[str, float]:
        """Fallback PDF text extraction using PyPDF2."""
        try:
            import PyPDF2
            text_parts = []
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text = page.extract_text() or ""
                    text_parts.append(text)
            combined = "\n".join(text_parts)
            return combined, 0.7 if len(combined) > 50 else 0.3
        except Exception as exc:
            logger.warning("PyPDF2 fallback failed: %s", exc)
            return "", 0.0

    async def _tesseract_fallback(self, file_path: str, psm: int = 3) -> Tuple[str, float]:
        """Fallback OCR using pytesseract."""
        try:
            import pytesseract
            from PIL import Image
            from pytesseract import Output

            image = Image.open(file_path)
            config = f"--psm {psm} --oem 3"
            data = pytesseract.image_to_data(image, config=config, output_type=Output.DICT)

            text_parts = []
            confs = []
            for i, text in enumerate(data["text"]):
                if text.strip():
                    text_parts.append(text)
                    confs.append(int(data["conf"][i]) if data["conf"][i] != "-1" else 0)

            text = " ".join(text_parts)
            avg_conf = sum(confs) / len(confs) / 100.0 if confs else 0.0
            return text, avg_conf
        except ImportError:
            logger.warning("Tesseract not installed — no OCR fallback available")
            return "", 0.0
        except Exception as exc:
            logger.warning("Tesseract fallback failed: %s", exc)
            return "", 0.0


# ─── Convenience ─────────────────────────────────────

parser_router = ParserRouter()
