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

import logging
import mimetypes
import os
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

# python-magic needs the native libmagic library, which is not present on a
# default Windows install (and optional elsewhere). Guard the import and fall
# back to extension-based sniffing via the stdlib.
try:
    import magic as _magic
except Exception as _magic_exc:  # ImportError, OSError from libmagic lookup
    _magic = None
    logger.info(
        "python-magic/libmagic unavailable (%s) — MIME sniffing falls back to file extensions via mimetypes.",
        _magic_exc,
    )

HAS_MAGIC = _magic is not None


def sniff_mime_type(file_path: str) -> str:
    """Best-effort MIME type for a file.

    Uses libmagic content sniffing when available, otherwise the filename
    extension. Returns "application/octet-stream" when nothing can be decided.
    """
    if HAS_MAGIC:
        try:
            return _magic.from_file(file_path, mime=True) or "application/octet-stream"
        except Exception as exc:
            logger.warning("libmagic sniff failed for %s: %s", file_path, exc)
    guessed, _ = mimetypes.guess_type(file_path)
    return guessed or "application/octet-stream"


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
            doc_type.value,
            doc_format.value,
            len(raw_text),
            extraction_confidence,
            elapsed,
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
        """Detect whether an image is handwritten rather than machine-printed.

        This is an image-content heuristic, not an ML classifier. It thresholds
        the image, extracts connected components (ink blobs) and looks at three
        signals that reliably separate print from handwriting:

          1. Baseline regularity — printed text sits on evenly spaced baselines,
             so the row-projection profile of ink is strongly periodic. Measured
             as the coefficient of variation of blob bottom-edge positions
             within each detected text row.
          2. Glyph size variance — printed glyphs are near-uniform in height;
             handwriting varies far more.
          3. Stroke-width variance — printed strokes have near-constant width
             (distance transform of the ink mask has low spread); pen strokes
             vary with pressure and speed.

        Returns True when at least two of the three signals look handwritten.
        Falls back to :meth:`_guess_handwriting_from_filename` when OpenCV or
        NumPy is unavailable.
        """
        try:
            import cv2
            import numpy as np
        except ImportError:
            logger.info("OpenCV/NumPy unavailable — handwriting detection degrades to a filename guess.")
            return self._guess_handwriting_from_filename(file_path)

        try:
            gray = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
            if gray is None:
                return self._guess_handwriting_from_filename(file_path)

            # Normalize scale so thresholds are resolution-independent
            max_side = max(gray.shape)
            if max_side > 1600:
                scale = 1600.0 / max_side
                gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

            # Adaptive threshold handles uneven lighting in phone photos.
            # Ink becomes 255 (foreground) on a 0 background.
            ink = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                31,
                10,
            )

            num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(ink, 8)

            # Keep plausible glyph-sized components; drop specks and page-sized blobs
            page_area = float(gray.shape[0] * gray.shape[1])
            heights: List[float] = []
            bottoms: List[float] = []
            for i in range(1, num_labels):
                x, y, w, h, area = (
                    stats[i, cv2.CC_STAT_LEFT],
                    stats[i, cv2.CC_STAT_TOP],
                    stats[i, cv2.CC_STAT_WIDTH],
                    stats[i, cv2.CC_STAT_HEIGHT],
                    stats[i, cv2.CC_STAT_AREA],
                )
                if area < 12 or area > page_area * 0.05:
                    continue
                if h < 4 or h > gray.shape[0] * 0.2:
                    continue
                heights.append(float(h))
                bottoms.append(float(y + h))

            if len(heights) < 25:
                # Too little ink to judge from content — fall back to the name.
                return self._guess_handwriting_from_filename(file_path)

            heights_arr = np.asarray(heights)
            bottoms_arr = np.asarray(bottoms)

            # (2) Glyph height variance
            height_cv = float(np.std(heights_arr) / max(np.mean(heights_arr), 1e-6))

            # (1) Baseline regularity: cluster bottoms into rows using the median
            # glyph height as the row tolerance, then measure spread within rows.
            tol = max(float(np.median(heights_arr)) * 0.5, 2.0)
            order = np.argsort(bottoms_arr)
            sorted_bottoms = bottoms_arr[order]
            rows: List[List[float]] = [[float(sorted_bottoms[0])]]
            for b in sorted_bottoms[1:]:
                if b - rows[-1][-1] <= tol:
                    rows[-1].append(float(b))
                else:
                    rows.append([float(b)])
            within_row_spread = [float(np.std(r)) for r in rows if len(r) >= 3]
            baseline_jitter = (
                float(np.mean(within_row_spread)) / max(float(np.median(heights_arr)), 1e-6)
                if within_row_spread
                else 1.0
            )

            # (3) Stroke-width variance via distance transform of the ink mask.
            dist = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
            stroke_radii = dist[dist > 0.5]
            if stroke_radii.size >= 50:
                stroke_cv = float(np.std(stroke_radii) / max(np.mean(stroke_radii), 1e-6))
            else:
                stroke_cv = 0.0

            signals = {
                "glyph_height_cv": height_cv > 0.45,
                "baseline_jitter": baseline_jitter > 0.18,
                "stroke_width_cv": stroke_cv > 0.55,
            }
            votes = sum(signals.values())
            logger.debug(
                "Handwriting heuristic for %s: height_cv=%.3f baseline_jitter=%.3f stroke_cv=%.3f votes=%d",
                os.path.basename(file_path),
                height_cv,
                baseline_jitter,
                stroke_cv,
                votes,
            )
            return votes >= 2
        except Exception as exc:
            logger.warning(
                "Handwriting detection failed for %s (%s) — falling back to filename guess.",
                file_path,
                exc,
            )
            return self._guess_handwriting_from_filename(file_path)

    @staticmethod
    def _guess_handwriting_from_filename(file_path: str) -> bool:
        """Guess handwriting purely from the file NAME — no image analysis.

        This inspects the basename for substrings like "rx"/"presc"/"hand". It is
        a last-resort fallback used only when image analysis is impossible; it
        knows nothing about the actual image content.
        """
        basename = os.path.basename(file_path).lower()
        handwriting_indicators = ["rx", "presc", "hand", "note", "scrip"]
        return any(indicator in basename for indicator in handwriting_indicators)

    async def _check_image_quality(self, file_path: str) -> list[str]:
        """Analyze image quality and return warning messages.

        Checks: blur (Laplacian variance), low contrast, dark/underexposed.
        Returns a list of human-readable warning strings (empty = all good).
        """
        try:
            import numpy as np
            from PIL import Image
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
        """Parse "handwritten" documents.

        The handwriting classifier (_detect_handwriting) uses image-content
        heuristics that misfire on stylized / high-contrast graphics — a
        screenshot of printed text on a bright background can look like
        handwriting to the row-projection detector. So we ALWAYS try
        RapidOCR (printed-text OCR) first. If it succeeds, great; if not,
        fall back to MedGemma (VLM).

        MedGemma also refuses some medical-looking images citing safety
        ("I cannot extract text from a medical document…") — we detect that
        specific refusal pattern and treat it as an empty result rather than
        propagating garbage back to the user.
        """
        # First attempt: fast printed-text OCR (RapidOCR under the surya_parse name).
        text, confidence = await self._ocr_service.surya_parse(file_path)
        if text.strip() and confidence >= 0.5:
            return text, confidence

        # Second attempt: VLM.
        vlm_text, vlm_conf = await self._ocr_service.medgemma_parse(file_path)
        if self._is_vlm_refusal(vlm_text):
            logger.info("MedGemma refused OCR; falling back to whatever RapidOCR produced.")
            return text, confidence  # may be empty — caller handles that
        if len(vlm_text) > len(text):
            return vlm_text, vlm_conf
        return text, confidence

    @staticmethod
    def _is_vlm_refusal(text: str) -> bool:
        """Detect the boilerplate refusal patterns MedGemma emits for medical images."""
        if not text:
            return False
        low = text.strip().lower()
        markers = (
            "i cannot extract",
            "i am not able to",
            "i'm sorry, but i cannot",
            "i am sorry, but i cannot",
            "cannot access external",
            "as an ai",
        )
        return any(m in low for m in markers)

    async def _parse_photo(self, file_path: str) -> Tuple[str, float]:
        """Parse photo: RapidOCR (surya_parse) first; MedGemma VLM re-check
        only if RapidOCR was unconfident. Guard against MedGemma's medical-image
        refusal replies so we don't return "I cannot extract text..." as OCR."""
        text, confidence = await self._ocr_service.surya_parse(file_path)
        if confidence < 0.5:
            text2, conf2 = await self._ocr_service.medgemma_parse(file_path)
            if not self._is_vlm_refusal(text2) and len(text2) > len(text):
                return text2, conf2
        return text, confidence

    async def _parse_unknown(self, file_path: str) -> Tuple[str, float]:
        """Try all parsers concurrently, return best result using weighted scoring.

        We fan out to every parser in parallel via asyncio.gather. Rationale:
        for a truly unknown document we would otherwise pay the full latency
        of Docling → Surya → Nanonets → MedGemma sequentially (often 20-40s).
        Running them concurrently means the wall-clock is bounded by the
        slowest single parser, not their sum. Exceptions from individual
        parsers are captured (return_exceptions=True) and skipped so one
        broken engine does not fail the whole request.
        """
        import asyncio

        parser_names = ["docling_parse", "surya_parse", "nanonets_ocr_parse", "medgemma_parse"]

        async def _safe_run(name: str) -> Tuple[str, float]:
            try:
                parser_fn = getattr(self._ocr_service, name)
                return await parser_fn(file_path)
            except Exception as exc:
                logger.debug("Parser %s failed on %s: %s", name, file_path, exc)
                return "", 0.0

        results = await asyncio.gather(*[_safe_run(n) for n in parser_names])

        best_text = ""
        best_score = 0.0
        best_conf = 0.0
        for text, conf in results:
            # Weighted score: longer text with decent confidence beats short text with high confidence
            score = len(text) * conf
            if score > best_score:
                best_text = text
                best_score = score
                best_conf = conf

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
            # Docling 2.x compiles its layout/detection models with
            # torch.compile by default. On a CPU-only torch install that JITs a
            # CUDA kernel (cuda_utils.c) which fails with "No working C++
            # compiler" / missing libcuda, killing the whole conversion. The
            # image ships g++ but no CUDA runtime, so disable compilation and
            # run eager — slower but correct on this hardware.
            #
            # Env var must be set BEFORE the docling import: pydantic-settings
            # reads DOCLING_* at instantiation time (module import). Mutating
            # the singleton afterwards is too late for engine options that
            # default from `defaults()`. Both are applied for belt-and-braces.
            import os as _docling_os

            _docling_os.environ.setdefault("DOCLING_INFERENCE_COMPILE_TORCH_MODELS", "false")

            from docling.document_converter import DocumentConverter

            try:
                from docling.datamodel.settings import settings as _docling_settings

                _docling_settings.inference.compile_torch_models = False
            except Exception:
                pass

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
        """Parse a scanned document / photo using RapidOCR (PaddleOCR ONNX port).

        Function name is kept as `surya_parse` so upstream routing code doesn't
        change, but the implementation is RapidOCR (Apache-2.0, ~15 MB deps,
        no revenue-cap license). Falls back to Tesseract on failure.

        Surya was replaced because its license restricts commercial use above
        certain revenue/funding thresholds; RapidOCR is fully permissive.
        """
        try:
            from rapidocr_onnxruntime import RapidOCR

            # Lazy singleton: RapidOCR loads ONNX models on init (~30 MB, a few
            # seconds cold-start). Keep a process-level instance so subsequent
            # calls are near-instant.
            if not hasattr(self, "_rapidocr") or self._rapidocr is None:
                logger.info("Loading RapidOCR (first call — expect ~2s cold-start)…")
                self._rapidocr = RapidOCR()
            ocr = self._rapidocr

            # RapidOCR accepts a file path directly; returns (results, elapse) where
            # results is a list of [box, text, confidence] tuples (or None if empty).
            result, _elapse = ocr(file_path)
            if not result:
                logger.info("RapidOCR returned no lines for %s", file_path)
                return "", 0.0

            lines = []
            confidences = []
            for item in result:
                # RapidOCR shape: [box, text, confidence]
                if isinstance(item, (list, tuple)) and len(item) >= 3:
                    _box, text, conf = item[0], item[1], item[2]
                    if text and str(text).strip():
                        lines.append(str(text))
                        try:
                            confidences.append(float(conf))
                        except (TypeError, ValueError):
                            pass
            text = "\n".join(lines).strip()
            if text:
                avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.85
                return text, round(avg_conf, 3)
        except ImportError:
            logger.info("RapidOCR not installed, falling back to Tesseract")
            return await self._tesseract_fallback(file_path)
        except Exception as exc:
            logger.warning("RapidOCR parsing failed: %s, falling back", exc)
            return await self._tesseract_fallback(file_path)
        return "", 0.0

    async def nanonets_ocr_parse(self, file_path: str) -> Tuple[str, float]:
        """Parse handwritten/printed text via MedGemma-4B (llama-server VLM).

        Function name kept as `nanonets_ocr_parse` for backward-compat with
        the routing table; internally this now delegates to `medgemma_parse`.

        Nanonets-OCR2-3B was ~6.5 GB and would OOM a 16 GB laptop. MedGemma
        is already resident in the always-on llama-server container, so this
        path costs zero additional RAM. Accuracy is lower than a dedicated
        handwritten-OCR model, but there are no published benchmarks showing
        Nanonets is meaningfully better for Indian handwritten prescriptions
        specifically, and the RAM saving is a hard win.
        """
        return await self.medgemma_parse(file_path)

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
        """Parse image using MedGemma-4B local VLM (GGUF via llama.cpp server).

        POSTs the image as a base64 data URL to the llama-server
        OpenAI-compatible /v1/chat/completions endpoint (mmproj loaded
        server-side). Falls back to basic Tesseract if the server is
        unreachable or returns no text.
        """
        import base64
        import mimetypes

        import httpx

        url = f"{settings.MEDGEMMA_SERVER_URL.rstrip('/')}/v1/chat/completions"
        try:
            mime = mimetypes.guess_type(file_path)[0] or "image/png"
            with open(file_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("ascii")

            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                            },
                            {"type": "text", "text": "Extract all text from this medical document."},
                        ],
                    }
                ],
                "max_tokens": 512,
                "temperature": 0.0,
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
            if text:
                return text, 0.75
        except Exception as exc:
            logger.warning("MedGemma (llama.cpp) parsing failed: %s, falling back", exc)
            return await self._tesseract_fallback(file_path)
        return "", 0.0

    # ─── VLM helper ───

    @staticmethod
    async def _vlm_generate(
        processor: Any,
        model: Any,
        image: Any,
        prompt: str,
        max_new_tokens: int = 512,
    ) -> str:
        """Run one image+prompt turn through a HF vision-language model.

        Builds the prompt with the processor's chat template when the model
        provides one (required by Qwen2-VL-style and Gemma-3-style checkpoints so
        the image placeholder tokens line up), otherwise passes the raw prompt.
        Only the newly generated tokens are decoded, so the echoed prompt is not
        mistaken for OCR output.
        """
        import asyncio

        import torch

        text_prompt = prompt
        if getattr(processor, "chat_template", None) or getattr(
            getattr(processor, "tokenizer", None), "chat_template", None
        ):
            messages = [
                {
                    "role": "user",
                    "content": [{"type": "image"}, {"type": "text", "text": prompt}],
                }
            ]
            text_prompt = processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )

        inputs = processor(text=text_prompt, images=image, return_tensors="pt")
        inputs = inputs.to(model.device)
        input_len = inputs["input_ids"].shape[-1]

        def _generate():
            with torch.inference_mode():
                return model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)

        outputs = await asyncio.to_thread(_generate)
        # Strip the prompt tokens; keep only the model's continuation.
        generated = outputs[0][input_len:]
        return processor.decode(generated, skip_special_tokens=True)

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
