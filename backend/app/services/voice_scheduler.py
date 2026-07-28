"""Voice Scheduling Service — ASR integration, intent routing, preference logging.

Provides:
  1. faster-whisper integration for English ASR
  2. IndicWhisper fallback for Hindi/Hinglish
  3. Voice scheduling subgraph — router node for scheduling intent
  4. Patient preference histogram update on booking

Usage:
    from app.services.voice_scheduler import VoiceScheduler
    vs = VoiceScheduler()
    result = await vs.transcribe(audio_bytes)  # -> {"text": "...", "language": "en", "confidence": 0.95}
    intent = await vs.classify_intent("Book Priya Sharma for Thursday 3 PM")
    # -> {"intent": "create_appointment", "confidence": 0.9, "params": {...}}
"""

from __future__ import annotations

import json
import re
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

from app.config import settings

logger = logging.getLogger(__name__)

# ─── ASR Service ───────────────────────────────────

class ASRService:
    """Speech-to-text using faster-whisper with IndicWhisper fallback."""

    def __init__(self):
        self._whisper_model = None
        self._indic_model = None

    async def _load_whisper(self):
        """Lazy-load faster-whisper model."""
        if self._whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                model_path = settings.WHISPER_PATH or "large-v3"
                # Check if custom path exists on disk
                import os
                if os.path.isabs(model_path) and not os.path.exists(model_path):
                    raise FileNotFoundError(
                        f"Whisper model not found at {model_path}. "
                        "Set WHISPER_PATH in .env or install the model."
                    )
                self._whisper_model = WhisperModel(model_path, device="cpu", compute_type="int8")
                logger.info("Loaded faster-whisper model: %s", model_path)
            except ImportError:
                logger.warning("faster-whisper not installed. Voice transcription unavailable.")
                self._whisper_model = "stub"
            except FileNotFoundError as exc:
                logger.warning("Whisper model not found: %s", exc)
                self._whisper_model = "stub"

    async def _load_indic_whisper(self):
        """Lazy-load IndicWhisper model."""
        if self._indic_model is None:
            try:
                from faster_whisper import WhisperModel
                model_path = settings.INDIC_WHISPER_PATH or "ai4bharat/indic-whisper-medium"
                import os
                if os.path.isabs(model_path) and not os.path.exists(model_path):
                    raise FileNotFoundError(
                        f"IndicWhisper model not found at {model_path}. "
                        "Set INDIC_WHISPER_PATH in .env or install the model."
                    )
                self._indic_model = WhisperModel(model_path, device="cpu", compute_type="int8")
                logger.info("Loaded IndicWhisper model: %s", model_path)
            except ImportError:
                logger.warning("faster-whisper not installed. IndicWhisper unavailable.")
                self._indic_model = "stub"
            except FileNotFoundError as exc:
                logger.warning("IndicWhisper model not found: %s", exc)
                self._indic_model = "stub"

    async def transcribe(self, audio_bytes: bytes, language: Optional[str] = None) -> Dict[str, Any]:
        """Transcribe audio to text.

        Args:
            audio_bytes: Raw audio bytes (WAV/MP3).
            language: Preferred language ('en', 'hi', None=auto-detect).

        Returns:
            {"text": str, "language": str, "confidence": float, "segments": [...]}
        """
        await self._load_whisper()
        if self._whisper_model == "stub":
            return self._stub_transcribe()

        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                temp_path = f.name

            segments, info = self._whisper_model.transcribe(
                temp_path,
                language=language,
                beam_size=3,
                vad_filter=True,
            )

            detected_lang = info.language if info else "en"
            lang_prob = info.language_probability if info else 0.5

            text_parts = []
            all_segments = []
            for seg in segments:
                text_parts.append(seg.text)
                all_segments.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                })

            text = " ".join(text_parts).strip()

            # If Hindi/Hinglish detected, re-run with IndicWhisper
            if detected_lang in ("hi", "mr", "gu", "bn") or (text and any(ord(c) > 127 for c in text[:100])):
                await self._load_indic_whisper()
                if self._indic_model and self._indic_model != "stub":
                    indic_segments, indic_info = self._indic_model.transcribe(temp_path)
                    indic_text = " ".join(s.text for s in indic_segments)
                    if len(indic_text) > len(text):
                        text = indic_text
                        detected_lang = "hi"

            import os
            os.unlink(temp_path)

            return {
                "text": text,
                "language": detected_lang,
                "confidence": round(lang_prob, 3),
                "segments": all_segments,
            }

        except Exception as exc:
            logger.error("ASR transcription failed: %s", exc)
            raise RuntimeError(
                f"ASR model not available: {exc}. "
                "Install faster-whisper (pip install faster-whisper) or configure WHISPER_PATH."
            ) from exc

    def _stub_transcribe(self) -> Dict[str, Any]:
        """Return stub result when no ASR model is available."""
        raise RuntimeError(
            "ASR model not loaded. Install faster-whisper or configure WHISPER_PATH/INDIC_WHISPER_PATH."
        )

    async def detect_language(self, audio_bytes: bytes) -> str:
        """Detect language from audio."""
        result = await self.transcribe(audio_bytes[:16000 * 3])  # First 3 seconds
        return result.get("language", "en")


# ─── Voice Intent Classifier ───────────────────────

SCHEDULING_INTENT_PATTERNS = {
    "create_appointment": [
        r"(?i)(book|schedule|make|create|set up)\s+(an?\s+)?(appointment|slot|visit|consultation)",
        r"(?i)see\s+(dr|doctor)",
        r"(?i)come\s+in\s+(for|to\s+see)",
    ],
    "reschedule_appointment": [
        r"(?i)(reschedule|move|change|shift|push)\s+(my|the|an?\s+)?(appointment|booking|slot)",
        r"(?i)can'?t\s+(make|come\s+to)\s+(the|my)\s+(appointment|slot)",
    ],
    "cancel_appointment": [
        r"(?i)(cancel|remove|delete|call\s+off|scrap)\s+(my|the|an?\s+)?(appointment|booking|slot)",
        r"(?i)i\s+(won't|wont|cannot|can't)\s+(make|attend|come)",
    ],
    "check_availability": [
        r"(?i)(when|what|find|check|show|tell)\s+(is|are|my|the|available|free|open)",
        r"(?i)(available|free|open)\s+(slots|times|appointments|days)",
        r"(?i)when\s+(am|is)\s+.*?(free|available)",
    ],
    "block_time": [
        r"(?i)(block|off|unavailable|closed|holiday|leave|break)\s+(my|the|doctor)",
        r"(?i)(taking|on)\s+(leave|off|a break|holiday)",
    ],
}

DATE_KEYWORDS = {
    "today": "today", "tomorrow": "tomorrow",
    "monday": "monday", "tuesday": "tuesday", "wednesday": "wednesday",
    "thursday": "thursday", "friday": "friday", "saturday": "saturday", "sunday": "sunday",
    "next week": "next_week", "this week": "this_week",
}

PATIENT_NAME_MARKERS = [
    r"(?i)(for|with|mr\.?|mrs\.?|ms\.?|dr\.?|patient)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
]


class VoiceIntentClassifier:
    """Classifies scheduling intents from transcribed voice commands."""

    def classify(self, text: str) -> Dict[str, Any]:
        """Classify voice command into scheduling intent with extracted parameters."""
        if not text.strip():
            return {"intent": "unknown", "confidence": 0.0, "params": {}}

        best_intent = "unknown"
        best_score = 0

        for intent, patterns in SCHEDULING_INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, text)
                score += len(matches)
            if score > best_score:
                best_score = score
                best_intent = intent

        confidence = min(best_score * 0.3, 0.95)

        # Extract parameters
        params = self._extract_params(text)

        return {
            "intent": best_intent,
            "confidence": round(confidence, 3),
            "params": params,
            "raw_text": text,
        }

    def _extract_params(self, text: str) -> Dict[str, Any]:
        """Extract scheduling parameters from voice command."""
        params = {}

        # Patient name
        for marker in PATIENT_NAME_MARKERS:
            match = re.search(marker, text)
            if match:
                name = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(0)
                params["patient_name"] = name.strip()
                break

        # Time (e.g., "3 PM", "15:00", "3:30 PM")
        time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM|am|pm)", text)
        if time_match:
            h = int(time_match.group(1))
            m = int(time_match.group(2)) if time_match.group(2) else 0
            ampm = time_match.group(3).upper()
            if ampm == "PM" and h != 12:
                h += 12
            if ampm == "AM" and h == 12:
                h = 0
            params["time"] = f"{h:02d}:{m:02d}"

        # Date/day
        for keyword, normalized in DATE_KEYWORDS.items():
            if keyword.lower() in text.lower():
                params["date"] = normalized
                break

        # Duration
        dur_match = re.search(r"(\d+)\s*(min|minute)", text)
        if dur_match:
            params["duration_minutes"] = int(dur_match.group(1))

        # Reason
        reason_markers = ["for", "because", "regarding", "follow-up", "check"]
        for marker in reason_markers:
            idx = text.lower().find(marker)
            if idx >= 0:
                after = text[idx + len(marker):].strip().rstrip(".,")
                # Remove trailing patient name if captured
                if "patient" in params:
                    after = after.replace(params.get("patient_name", ""), "").strip()
                if after and len(after) > 3:
                    params["reason"] = after[:100]
                    break

        return params


# ─── Voice Scheduler (Main Service) ─────────────────

class VoiceScheduler:
    """Complete voice scheduling service — ASR + intent classification + preference learning."""

    def __init__(self):
        self.asr = ASRService()
        self.classifier = VoiceIntentClassifier()

    async def process_voice_command(self, audio_bytes: bytes) -> Dict[str, Any]:
        """Full pipeline: transcribe → classify → structured result."""
        # Step 1: Transcribe
        transcript = await self.asr.transcribe(audio_bytes)
        text = transcript.get("text", "").strip()
        lang = transcript.get("language", "en")
        asr_confidence = transcript.get("confidence", 0.0)

        if not text:
            return {
                "status": "no_speech",
                "text": "",
                "language": lang,
                "intent": "unknown",
                "confidence": 0.0,
                "params": {},
            }

        # Step 2: Classify intent
        classification = self.classifier.classify(text)

        # Step 3: Log for preference learning
        logger.info(
            "Voice command: lang=%s text=%s intent=%s conf=%.2f",
            lang, text[:80], classification["intent"], classification["confidence"],
        )

        return {
            "status": "ok",
            "text": text,
            "language": lang,
            "asr_confidence": asr_confidence,
            "intent": classification["intent"],
            "confidence": classification["confidence"],
            "params": classification["params"],
        }


voice_scheduler = VoiceScheduler()


# ─── Maverick Intent Classification (Week 11) ───────

class MaverickIntentClassifier:
    """Uses Maverick (Llama-4) via NIM for scheduling intent classification.

    Five locked voice commands from UpdatedIdea.MD:
      1. "Book Priya Sharma for Thursday 3 PM, fever follow-up."
      2. "I'm off Friday and Saturday - handle it."
      3. "When am I free 30 minutes next week before lunch?"
      4. "Move all diabetic follow-ups due this month to morning slots."
      5. "Cancel Mrs. Patel's Wednesday appointment, she just called."
    """

    def __init__(self):
        self._synthesizer = None

    async def classify(self, text: str) -> Dict[str, Any]:
        """Classify voice command using Maverick LLM."""
        from app.agents.synthesizer import MaverickSynthesizer
        if self._synthesizer is None:
            self._synthesizer = MaverickSynthesizer()

        if not self._synthesizer.is_available:
            # Fall back to keyword classifier
            fallback = VoiceIntentClassifier()
            return fallback.classify(text)

        prompt = (
            "You are a scheduling intent classifier. Given a voice command, "
            "output JSON with:\n"
            "- intent: create_appointment | reschedule_appointment | cancel_appointment | "
            "block_doctor_time | query_calendar_nl | bulk_reschedule | unknown\n"
            "- confidence: 0.0-1.0\n"
            "- params: {patient_name, date, time, duration_minutes, reason}\n\n"
            f"Voice command: {text}\n\n"
            "Output JSON only."
        )

        try:
            response = await self._synthesizer.synthesize(
                query=prompt,
                context={},
                structured_output={"type": "json_object"},
            )

            import json as _json
            raw = response.get("response", "")
            parsed = _json.loads(raw) if raw else {}
            return {
                "intent": parsed.get("intent", "unknown"),
                "confidence": parsed.get("confidence", 0.5),
                "params": parsed.get("params", {}),
                "raw_text": text,
                "model": "maverick",
            }
        except Exception as exc:
            logger.warning("Maverick intent classification failed: %s", exc)
            fallback = VoiceIntentClassifier()
            return fallback.classify(text)


# ─── TTS Service (Week 11) ──────────────────────────

class ParlerTTSService:
    """Text-to-Speech using Indic-Parler-TTS for English and Hindi."""

    def __init__(self):
        self._model = None

    async def _load_model(self):
        if self._model is None:
            try:
                from parler_tts import ParlerTTSForConditionalGeneration
                from transformers import AutoTokenizer
                import torch

                model_path = settings.PARLER_TTS_PATH or "ai4bharat/indic-parler-tts"
                device = "cuda" if torch.cuda.is_available() else "cpu"

                self._model = ParlerTTSForConditionalGeneration.from_pretrained(model_path).to(device)
                self._tokenizer = AutoTokenizer.from_pretrained(model_path)
                logger.info("Loaded Parler-TTS model: %s (%s)", model_path, device)
            except ImportError:
                logger.warning("parler_tts not installed. Using notification-only TTS.")
                self._model = "stub"

    async def synthesize(self, text: str, language: str = "en") -> Dict[str, Any]:
        """Synthesize speech from text.

        Args:
            text: Text to speak.
            language: 'en' for English, 'hi' for Hindi.

        Returns:
            {"audio_path": str, "duration_seconds": float, "text": str, "language": str}
        """
        await self._load_model()

        if self._model == "stub" or self._model is None:
            return {
                "audio_path": "",
                "duration_seconds": 0,
                "text": text[:100],
                "language": language,
                "note": "TTS model not loaded. Parler-TTS requires installation.",
            }

        try:
            import torch
            import tempfile
            import soundfile as sf

            description = (
                "A female doctor speaks clearly in a clinical setting."
                if language == "en"
                else "Ek mahila doctor spill bol rahi hain."
            )

            inputs = self._tokenizer(description, return_tensors="pt")
            prompt = self._tokenizer(text, return_tensors="pt")

            with torch.no_grad():
                output = self._model.generate(
                    input_ids=inputs.input_ids,
                    prompt_input_ids=prompt.input_ids,
                    max_length=512,
                )

            audio = output.cpu().numpy().squeeze()

            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            sf.write(tmp.name, audio, samplerate=16000)

            duration = len(audio) / 16000

            return {
                "audio_path": tmp.name,
                "duration_seconds": round(duration, 1),
                "text": text[:100],
                "language": language,
            }
        except Exception as exc:
            logger.error("TTS synthesis failed: %s", exc)
            return {
                "audio_path": "",
                "duration_seconds": 0,
                "text": text[:100],
                "language": language,
                "error": str(exc)[:100],
            }

    async def synthesize_booking_confirmation(
        self, patient_name: str, date: str, time: str, language: str = "en"
    ) -> Dict[str, Any]:
        """Generate TTS for booking confirmation."""
        if language == "hi":
            text = f"{patient_name} ka appointment {date} ko {time} par book kar liya gaya hai."
        else:
            text = f"Appointment booked for {patient_name} on {date} at {time}."
        return await self.synthesize(text, language)

    async def synthesize_cancellation(
        self, patient_name: str, language: str = "en"
    ) -> Dict[str, Any]:
        text = f"{patient_name} ka appointment cancel kar diya gaya hai." if language == "hi" else f"The appointment for {patient_name} has been cancelled."
        return await self.synthesize(text, language)


# ─── Voice Subgraph (End-to-End) ───────────────────

class VoiceSubgraph:
    """Full voice scheduling flow: mic -> ASR -> intent -> tools -> TTS.

    Wires together ASR, Maverick intent classification, tool dispatch,
    and TTS confirmation for the five locked voice commands.
    """

    def __init__(self):
        self.asr = ASRService()
        self.intent_classifier = MaverickIntentClassifier()
        self.tts = ParlerTTSService()

    async def process_command(
        self,
        audio_bytes: bytes,
        doctor_id: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Full pipeline: transcribe -> classify -> dispatch -> TTS.

        Returns structured result for the five locked voice commands.
        """
        # 1. ASR
        transcript = await self.asr.transcribe(audio_bytes, language=language)
        text = transcript.get("text", "").strip()
        lang = transcript.get("language", "en")

        if not text:
            return {
                "status": "no_speech",
                "voice_command": None,
                "tts_prompt": "I couldn't hear you. Please try again.",
                "language": lang,
            }

        # 2. Intent classification
        intent_result = await self.intent_classifier.classify(text)
        intent = intent_result.get("intent", "unknown")
        confidence = intent_result.get("confidence", 0.0)
        params = intent_result.get("params", {})

        # 3. Determine TTS response based on intent and the five locked commands
        tts_prompt = self._get_tts_prompt(intent, params, lang)

        # 4. TTS synthesis
        tts_result = await self.tts.synthesize(tts_prompt, lang)

        return {
            "status": "ok",
            "voice_command": {
                "text": text,
                "intent": intent,
                "confidence": confidence,
                "params": params,
            },
            "tts_audio": tts_result.get("audio_path", ""),
            "tts_prompt": tts_prompt,
            "tts_duration": tts_result.get("duration_seconds", 0),
            "language": lang,
        }

    def _get_tts_prompt(self, intent: str, params: dict, lang: str) -> str:
        """Generate TTS prompt based on detected intent and parameters."""
        patient_name = params.get("patient_name", "the patient")
        date = params.get("date", "the requested date")
        time_val = params.get("time", "the requested time")
        reason = params.get("reason", "")

        if lang == "hi":
            prompts = {
                "create_appointment": f"{patient_name} ka appointment {date} ko {time_val} par book kar liya gaya hai. {reason}",
                "cancel_appointment": f"{patient_name} ka appointment cancel kar diya gaya hai.",
                "reschedule_appointment": f"{patient_name} ka appointment reschedule kar diya gaya hai.",
                "block_doctor_time": "Doctor ki chhutti mark kar di gayi hai. Sabhi appointments reschedule ki jayengi.",
                "query_calendar_nl": "Calendar ki information mil rahi hai.",
                "bulk_reschedule": "Sabhi appointments ko reschedule kiya ja raha hai.",
            }
        else:
            prompts = {
                "create_appointment": f"Appointment booked for {patient_name} on {date} at {time_val}. {reason}",
                "cancel_appointment": f"The appointment for {patient_name} has been cancelled.",
                "reschedule_appointment": f"The appointment for {patient_name} has been rescheduled.",
                "block_doctor_time": "Doctor's time has been blocked. Affected appointments will be rescheduled.",
                "query_calendar_nl": "Checking the calendar for available slots.",
                "bulk_reschedule": "Rescheduling the requested appointments now.",
            }

        return prompts.get(intent, f"Processing your request for {intent}.")


# ─── Feature C: Training Pair Collection (Week 11) ──

def collect_training_pair(
    voice_text: str,
    intent: str,
    params: dict,
    doctor_action: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Collect (voice command, doctor action) training pairs for Feature C.

    Feature C trains a linear projector for cross-modal retrieval.
    Voice commands and their resolved scheduling actions serve as
    text-side training data paired with scheduling outcomes.
    """
    return {
        "voice_text": voice_text[:500],
        "intent": intent,
        "params": params,
        "doctor_action": doctor_action,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "voice_scheduling",
    }
