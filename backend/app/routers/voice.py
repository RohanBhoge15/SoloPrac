"""Voice Router — speech-to-text transcription endpoint.

Endpoints:
    POST /voice/transcribe — Transcribe audio to text using faster-whisper
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Form
from typing import Optional

from app.dependencies import get_current_doctor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio file (wav, mp3, webm, m4a, ogg)"),
    language: Optional[str] = Form(None, description="Optional language hint (en, hi, etc.)"),
    doctor=Depends(get_current_doctor),
):
    """Transcribe audio to text using faster-whisper with IndicWhisper fallback.

    Accepts audio from browser MediaRecorder API.
    Returns transcribed text with language detection and confidence score.
    """
    # Validate file type
    allowed_types = {
        "audio/wav", "audio/wave", "audio/x-wav",
        "audio/mp3", "audio/mpeg",
        "audio/webm",
        "audio/m4a", "audio/x-m4a",
        "audio/ogg", "audio/x-ogg",
    }
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio type: {file.content_type}. Allowed: wav, mp3, webm, m4a, ogg",
        )

    # Read audio bytes
    audio_bytes = await file.read()
    if len(audio_bytes) < 1000:
        raise HTTPException(status_code=400, detail="Audio file too small — no speech detected")
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio file too large — max 25MB")

    try:
        from app.services.voice_scheduler import ASRService
        asr = ASRService()
        result = await asr.transcribe(audio_bytes, language=language)
        return {
            "text": result.get("text", ""),
            "language": result.get("language", "en"),
            "confidence": result.get("confidence", 0.0),
        }
    except RuntimeError as exc:
        # ASR model not installed — clear error for user
        logger.warning("ASR not available: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Voice transcription not available — ASR model not installed. Contact admin to install faster-whisper.",
        )
    except Exception as exc:
        logger.error("Transcription failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")
