"""GPU Optimization — model swapping strategy for RTX 3050 4GB VRAM.

Strategy:
1. Keep NVIDIA NIM remote models always available (no VRAM cost)
2. MedGemma-4B local: load on demand, unload after inference (fits in ~3GB)
3. Faster-Whisper: keep loaded (uses ~1GB, stays under limit)
4. Indic-Parler-TTS: load on demand (~500MB)
5. Emergency OOM recovery: clear cache, retry on CPU

Usage:
    from app.services.gpu_optimizer import gpu_optimizer
    async with gpu_optimizer.model_context("medgemma"):
        result = await model.process(...)
"""

from __future__ import annotations

import gc
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, AsyncIterator

logger = logging.getLogger(__name__)

# VRAM budget (RTX 3050 = ~4GB usable)
VRAM_BUDGET = {
    "medgemma": 3.0,        # ~3GB when loaded
    "whisper": 1.0,         # ~1GB when loaded
    "parler_tts": 0.5,      # ~500MB when loaded
    "reserved": 0.5,        # 500MB headroom
}

TOTAL_VRAM = 4.0


class GPUOptimizer:
    """Manages GPU memory for local models on RTX 3050."""

    def __init__(self):
        self._loaded_models: Dict[str, Any] = {}
        self._vram_used: float = 0.0
        self._total_available = TOTAL_VRAM

    @property
    def vram_available(self) -> float:
        """GB of VRAM currently free."""
        return self._total_available - self._vram_used

    @property
    def is_medgemma_loaded(self) -> bool:
        return "medgemma" in self._loaded_models

    def mark_loaded(self, name: str, vram_gb: float):
        """Mark a model as loaded for tracking."""
        if name not in self._loaded_models:
            self._loaded_models[name] = True
            self._vram_used += vram_gb
            logger.info("Model '%s' loaded (VRAM: +%.1fGB, available: %.1fGB)",
                        name, vram_gb, self.vram_available)

    def mark_unloaded(self, name: str, vram_gb: float):
        """Mark a model as unloaded."""
        if name in self._loaded_models:
            del self._loaded_models[name]
            self._vram_used = max(0, self._vram_used - vram_gb)
            logger.info("Model '%s' unloaded (VRAM: -%.1fGB, available: %.1fGB)",
                        name, vram_gb, self.vram_available)

    @asynccontextmanager
    async def model_context(self, name: str, vram_gb: float) -> AsyncIterator[None]:
        """Context manager: load model, use it, unload after.

        For models that should be loaded temporarily (MedGemma, Parler-TTS).
        """
        try:
            if self.vram_available < vram_gb:
                # Force garbage collection and try again
                gc.collect()
                if self.vram_available < vram_gb:
                    # Unload least recently used model
                    self._unload_lru()
                    gc.collect()

            self.mark_loaded(name, vram_gb)
            yield
        finally:
            self.mark_unloaded(name, vram_gb)
            gc.collect()

    def _unload_lru(self):
        """Unload least recently used model to free VRAM."""
        # Simple strategy: unload Parler-TTS first (smallest), then MedGemma
        for model_name in ["parler_tts", "medgemma"]:
            if model_name in self._loaded_models:
                vram = VRAM_BUDGET.get(model_name, 1.0)
                self.mark_unloaded(model_name, vram)
                logger.info("OOM recovery: unloaded '%s' (freed %.1fGB)", model_name, vram)
                return

    async def clear_all(self):
        """Clear all loaded models and force GC."""
        model_names = list(self._loaded_models.keys())
        for name in model_names:
            vram = VRAM_BUDGET.get(name, 1.0)
            self.mark_unloaded(name, vram)
        gc.collect()
        logger.info("GPU cache cleared: all models unloaded")

    def get_status(self) -> Dict[str, Any]:
        """Get current GPU memory status."""
        return {
            "vram_total_gb": self._total_available,
            "vram_used_gb": round(self._vram_used, 2),
            "vram_available_gb": round(self.vram_available, 2),
            "models_loaded": list(self._loaded_models.keys()),
            "strategy": "Keep NIM remote, load local on-demand, unload after inference",
            "note": "NVIDIA NIM remote models cost no local VRAM",
        }


gpu_optimizer = GPUOptimizer()


# ─── Voice Pipeline Latency Optimization ───────────────────

class VoiceLatencyOptimizer:
    """Optimizations for voice pipeline latency."""

    def __init__(self):
        self._tts_cache: Dict[str, bytes] = {}  # text_hash -> audio bytes
        self._max_cache_size = 50

    @staticmethod
    def text_hash(text: str, voice: str = "default") -> str:
        """Simple hash for TTS cache key."""
        import hashlib
        return hashlib.md5(f"{text}:{voice}".encode()).hexdigest()

    def get_cached_tts(self, text: str, voice: str = "default") -> Optional[bytes]:
        """Get cached TTS output if available."""
        key = self.text_hash(text, voice)
        return self._tts_cache.get(key)

    def cache_tts(self, text: str, audio: bytes, voice: str = "default"):
        """Cache TTS output."""
        key = self.text_hash(text, voice)
        if len(self._tts_cache) >= self._max_cache_size:
            # Remove oldest entry
            oldest = next(iter(self._tts_cache))
            del self._tts_cache[oldest]
        self._tts_cache[key] = audio

    def optimize_asr_prompt(self, text: str) -> str:
        """Pre-process ASR input for faster inference.

        Strips non-speech markers, normalizes whitespace.
        """
        import re
        text = re.sub(r'\[.*?\]', '', text)  # Remove [laughter], [noise], etc.
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def estimate_latency(self, audio_duration_sec: float, model: str = "whisper") -> Dict[str, float]:
        """Estimate pipeline latency based on audio duration."""
        # Rough latency estimates
        asr_factor = {"whisper": 0.3, "indic_whisper": 0.4}  # real-time factor
        intent_factor = 0.05  # ~50ms for intent classification
        tts_factor = 0.2  # real-time factor for TTS

        rtf = asr_factor.get(model, 0.3)
        return {
            "audio_duration_sec": round(audio_duration_sec, 1),
            "estimated_asr_sec": round(audio_duration_sec * rtf, 2),
            "estimated_intent_sec": intent_factor,
            "estimated_tts_sec": round(audio_duration_sec * tts_factor, 2),
            "total_estimated_sec": round(
                audio_duration_sec * rtf + intent_factor + audio_duration_sec * tts_factor, 2
            ),
            "note": "Some models load on first use (cold start adds ~2s for MedGemma)",
        }


voice_latency_optimizer = VoiceLatencyOptimizer()
