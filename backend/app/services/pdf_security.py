"""PDF Security Service — Watermarks, QR codes, audit logging, two-step confirmation.

Dev's Week 9 tasks:
  1. PDF security — watermark, disclaimer footer enforcement
  2. QR code generation for certificate verification
  3. Audit logging — every PDF generate/print/email logged
  4. Two-step confirmation before any patient-facing PDF

Usage:
    from app.services.pdf_security import PDFSecurityService
    sec = PDFSecurityService()
    watermarked = await sec.add_watermark(pdf_path, "CONFIDENTIAL")
    qr_path = await sec.generate_qr_code("SPC-A1B2-C3D4")
    await sec.log_pdf_event(db, doctor_id, "generate", "prescription", rx_id)
"""

from __future__ import annotations

import os
import io
import uuid
import logging
import qrcode
from typing import Optional
from datetime import datetime, timezone
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from PyPDF2 import PdfReader, PdfWriter

import fitz  # PyMuPDF - for QR embedding

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_DOCTOR_NAME = "Dr. [Name]"


def watermark_text(doctor_name: str = DEFAULT_DOCTOR_NAME) -> str:
    return f"AI-Assisted Draft — Validated by Dr. {doctor_name.replace('Dr. ', '')}"


def disclaimer_text(doctor_name: str = DEFAULT_DOCTOR_NAME) -> str:
    return f"AI-Assisted Draft — Validated by Dr. {doctor_name.replace('Dr. ', '')}. Not a substitute for clinical judgement."

class PDFSecurityService:
    """Security layer for all PDF operations."""

    def __init__(self):
        self.watermark_color = HexColor("#E5E7EB")  # Light gray
        self.watermark_opacity = 0.15

    # ─── Watermark & Disclaimer ───

    async def add_watermark(self, input_path: str, output_path: Optional[str] = None, doctor_name: Optional[str] = None, custom_text: Optional[str] = None) -> str:
        """Add a semi-transparent watermark to every page of a PDF.

        Follows UpdatedIdea.MD spec: 'AI-assisted draft — validated by Dr. <name>'

        Args:
            input_path: Path to the source PDF.
            output_path: Where to save the watermarked PDF. If None, overwrites input.
            doctor_name: Doctor's name for the personalized disclaimer.
            custom_text: Custom watermark text. If not provided, uses doctor_name.

        Returns:
            Path to the watermarked PDF.
        """
        if custom_text:
            text = custom_text
        else:
            text = watermark_text(doctor_name or DEFAULT_DOCTOR_NAME)
        output = output_path or input_path

        reader = PdfReader(input_path)
        writer = PdfWriter()

        # Create watermark page
        watermark_buffer = io.BytesIO()
        c = canvas.Canvas(watermark_buffer, pagesize=A5)
        c.setFont("Helvetica", 36)
        c.setFillColor(HexColor("#9CA3AF"))  # Gray-400
        c.setFillAlpha(self.watermark_opacity)

        # Diagonal watermark
        c.saveState()
        c.translate(A5[0] / 2, A5[1] / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, text)
        c.restoreState()

        # Disclaimer at bottom
        c.setFont("Helvetica", 7)
        c.setFillColor(HexColor("#94A3B8"))  # Gray-400
        c.setFillAlpha(1.0)
        c.drawCentredString(A5[0] / 2, 10 * mm, disclaimer_text(doctor_name or DEFAULT_DOCTOR_NAME))

        c.save()
        watermark_buffer.seek(0)
        watermark_pdf = PdfReader(watermark_buffer)
        watermark_page = watermark_pdf.pages[0]

        # Merge watermark onto each page
        for page in reader.pages:
            page.merge_page(watermark_page)
            writer.add_page(page)

        # Write output
        with open(output, "wb") as f:
            writer.write(f)

        logger.info("Watermark applied to %s -> %s", input_path, output)
        return output

    async def add_disclaimer(self, input_path: str, output_path: Optional[str] = None, doctor_name: Optional[str] = None, custom_text: Optional[str] = None) -> str:
        """Add disclaimer footer to each page (no watermark).

        Follows UpdatedIdea.MD spec: 'AI-assisted draft — validated by Dr. <name>'
        """
        output = output_path or input_path
        reader = PdfReader(input_path)
        writer = PdfWriter()

        if custom_text:
            d_text = custom_text
        else:
            d_text = disclaimer_text(doctor_name or DEFAULT_DOCTOR_NAME)

        for page in reader.pages:
            c = canvas.Canvas(io.BytesIO(), pagesize=page.mediabox)
            c.setFont("Helvetica", 6.5)
            c.setFillColor(HexColor("#94A3B8"))
            c.drawCentredString(page.mediabox.width / 2, 8 * mm, d_text)
            c.save()
            c._buffer.seek(0)
            disclaimer_pdf = PdfReader(c._buffer)
            page.merge_page(disclaimer_pdf.pages[0])
            writer.add_page(page)

        with open(output, "wb") as f:
            writer.write(f)
        return output

    # ─── QR Code Generation ───

    async def generate_qr_code(self, data: str, output_path: Optional[str] = None, size: int = 100) -> str:
        """Generate a QR code image for certificate verification.

        Args:
            data: Data to encode (e.g., verification URL or code).
            output_path: Where to save the PNG. Auto-generated if None.
            size: QR code size in pixels.

        Returns:
            Path to the generated QR code PNG.
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((size, size))

        output = output_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "outputs", "qrcodes",
            f"qr_{uuid.uuid4().hex[:8]}.png"
        )
        os.makedirs(os.path.dirname(output), exist_ok=True)
        img.save(output)
        logger.info("QR code generated: %s -> %s", data[:50], output)
        return output

    async def embed_qr_in_pdf(self, pdf_path: str, qr_data: str, position: str = "bottom-right") -> str:
        """Embed a QR code into the last page of a PDF using PyMuPDF.

        Args:
            pdf_path: Path to the source PDF.
            qr_data: Data to encode in QR.
            position: Where to place QR ('bottom-right', 'bottom-left', 'top-right', 'top-left').

        Returns:
            Path to the modified PDF.
        """
        # Generate QR image
        qr_path = await self.generate_qr_code(qr_data, size=120)

        # Open PDF with PyMuPDF
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            doc.close()
            raise ValueError("PDF has no pages")

        # Get last page
        page = doc[-1]
        page_rect = page.rect
        page_width = page_rect.width
        page_height = page_rect.height

        # QR size in points (1/72 inch)
        qr_size = 72  # 1 inch square
        margin = 20

        positions = {
            "bottom-right": (page_width - qr_size - margin, page_height - qr_size - margin),
            "bottom-left": (margin, page_height - qr_size - margin),
            "top-right": (page_width - qr_size - margin, margin),
            "top-left": (margin, margin),
        }
        x, y = positions.get(position, positions["bottom-right"])

        # Create rect for QR image
        qr_rect = fitz.Rect(x, y, x + qr_size, y + qr_size)

        # Insert QR image on last page
        page.insert_image(qr_rect, filename=qr_path)

        # Save to new file
        output_path = pdf_path.replace(".pdf", "_qr.pdf")
        doc.save(output_path)
        doc.close()

        # Clean up QR image file
        try:
            os.remove(qr_path)
        except OSError:
            pass

        logger.info("QR code embedded in PDF: %s -> %s", pdf_path, output_path)
        return output_path

    # ─── Audit Logging ───

    @staticmethod
    async def log_pdf_event(
        db_session,
        doctor_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: str,
        details: Optional[dict] = None,
    ):
        """Log a PDF-related event to the audit trail.

        Actions: generate, print, email, download, verify
        Resource types: prescription, invoice, certificate
        """
        try:
            from app.models import AuditLog
            entry = AuditLog(
                doctor_id=doctor_id,
                patient_id=details.get("patient_id") if details else None,
                actor=f"doctor:{doctor_id}",
                action=f"pdf:{action}",
                resource_type=resource_type,
                resource_id=uuid.UUID(resource_id),
                payload_jsonb={
                    **(details or {}),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            db_session.add(entry)
            await db_session.commit()
        except Exception as exc:
            logger.warning("PDF audit log failed (non-blocking): %s", exc)
            await db_session.rollback()

    # ─── Two-Step Confirmation ───

    class TwoStepConfirmation:
        """Manages two-step confirmation for patient-facing PDFs."""

        def __init__(self):
            self._pending: dict = {}

        async def request_confirmation(
            self,
            doctor_id: uuid.UUID,
            resource_type: str,
            resource_id: str,
            reason: str = "",
        ) -> str:
            """Request confirmation for a patient-facing PDF action.

            Returns a confirmation token that must be used in the confirm step.
            """
            token = uuid.uuid4().hex
            self._pending[token] = {
                "doctor_id": doctor_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "reason": reason,
                "created_at": datetime.now(timezone.utc),
            }
            return token

        async def confirm(
            self,
            token: str,
            doctor_id: uuid.UUID,
        ) -> dict:
            """Confirm a pending action. Returns the original request details if valid."""
            pending = self._pending.pop(token, None)
            if not pending:
                raise ValueError("Invalid or expired confirmation token")
            if pending["doctor_id"] != doctor_id:
                raise ValueError("Confirmation token belongs to a different doctor")
            return pending

    # ─── Health Check ───

    async def get_security_status(self) -> dict:
        return {
            "watermark": True,
            "disclaimer_footer": True,
            "qr_generation": True,
            "audit_logging": True,
            "two_step_confirmation": True,
            "watermark_format": watermark_text("Dr. [Name]"),
            "disclaimer_format": disclaimer_text("Dr. [Name]"),
            "spec_reference": "UpdatedIdea.MD: 'AI-assisted draft — validated by Dr. <name>. Not a substitute for clinical judgement.'",
        }