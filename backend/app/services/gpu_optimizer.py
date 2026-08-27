"""GPU Optimizer — Model swapping strategy for RTX 3050 (4-6 GB VRAM).

Manages loading/unloading of local models to fit within VRAM constraints:
- MedGemma-4B-IT (Q4): ~3 GB
- faster-whisper large-v3: ~2 GB
- Indic-Parler-TTS: ~2 GB

Strategy: Only ONE model on GPU at a time. Swap on demand.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import torch

from app.config import settings

logger = logging.getLogger(__name__)


class ModelName(str, Enum):
    MEDGEMMA = "medgemma"
    WHISPER = "whisper"
    INDIC_WHISPER = "indic_whisper"
    PARLER_TTS = "parler_tts"


@dataclass
class ModelInfo:
    name: ModelName
    path: str
    vram_gb: float
    loaded: bool = False
    model_obj: Any = None
    processor: Any = None


# VRAM budget per model (RTX 3050 4-6 GB)
MODEL_CONFIGS: Dict[ModelName, ModelInfo] = {
    ModelName.MEDGEMMA: ModelInfo(
        name=ModelName.MEDGEMMA,
        path=settings.MEDGEMMA_PATH or "/models/medgemma-4b-it",
        vram_gb=3.0,
    ),
    ModelName.WHISPER: ModelInfo(
        name=ModelName.WHISPER,
        path=settings.WHISPER_PATH or "/models/faster-whisper-large-v3",
        vram_gb=2.0,
    ),
    ModelName.INDIC_WHISPER: ModelInfo(
        name=ModelName.INDIC_WHISPER,
        path=settings.INDIC_WHISPER_PATH or "/models/indic-whisper",
        vram_gb=2.0,
    ),
    ModelName.PARLER_TTS: ModelInfo(
        name=ModelName.PARLER_TTS,
        path=settings.PARLER_TTS_PATH or "/models/indic-parler-tts",
        vram_gb=2.0,
    ),
}


class GPUOptimizer:
    """Manages GPU model loading with swap strategy for RTX 3050."""

    def __init__(self):
        self._current_model: Optional[ModelName] = None
        self._lock = asyncio.Lock()
        self._models: Dict[ModelName, ModelInfo] = MODEL_CONFIGS.copy()
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._vram_total_gb = self._get_vram_total()

    def _get_vram_total(self) -> float:
        """Get total VRAM in GB."""
        if torch.cuda.is_available():
            return torch.cuda.get_device_properties(0).total_memory / (1024**3)
        return 0.0

    @property
    def current_model(self) -> Optional[ModelName]:
        return self._current_model

    @property
    def vram_total_gb(self) -> float:
        return self._vram_total_gb

    @property
    def vram_available_gb(self) -> float:
        if not torch.cuda.is_available():
            return 0.0
        allocated = torch.cuda.memory_allocated() / (1024**3)
        return self._vram_total_gb - allocated

    async def ensure_model_loaded(self, model_name: ModelName) -> ModelInfo:
        """Ensure a model is loaded on GPU, swapping if necessary.

        Args:
            model_name: The model to load

        Returns:
            ModelInfo with loaded model object
        """
        async with self._lock:
            model_info = self._models.get(model_name)
            if not model_info:
                raise ValueError(f"Unknown model: {model_name}")

            if model_info.loaded and model_info.model_obj is not None:
                logger.info(f"Model {model_name.value} already loaded")
                return model_info

            # Need to swap - unload current model first
            if self._current_model and self._current_model != model_name:
                await self._unload_model(self._current_model)

            # Load the requested model
            await self._load_model(model_name)
            return model_info

    async def _load_model(self, model_name: ModelName) -> None:
        """Load a specific model onto GPU."""
        model_info = self._models[model_name]

        if not os.path.exists(model_info.path):
            raise FileNotFoundError(f"Model not found at {model_info.path}")

        logger.info(f"Loading {model_name.value} onto GPU (VRAM budget: {model_info.vram_gb} GB)...")

        try:
            if model_name == ModelName.MEDGEMMA:
                await self._load_medgemma(model_info)
            elif model_name == ModelName.WHISPER:
                await self._load_whisper(model_info)
            elif model_name == ModelName.INDIC_WHISPER:
                await self._load_indic_whisper(model_info)
            elif model_name == ModelName.PARLER_TTS:
                await self._load_parler_tts(model_info)

            model_info.loaded = True
            self._current_model = model_name
            logger.info(f"Successfully loaded {model_name.value} on GPU")

        except Exception as e:
            logger.error(f"Failed to load {model_name.value}: {e}")
            model_info.loaded = False
            model_info.model_obj = None
            model_info.processor = None
            raise

    async def _load_medgemma(self, model_info: ModelInfo) -> None:
        """Load MedGemma-4B-IT model."""
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        model_info.model_obj = AutoModelForCausalLM.from_pretrained(
            model_info.path,
            torch_dtype=torch.float16,
            device_map="cuda",
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        model_info.processor = AutoProcessor.from_pretrained(model_info.path, trust_remote_code=True)

    async def _load_whisper(self, model_info: ModelInfo) -> None:
        """Load faster-whisper large-v3 model."""
        from faster_whisper import WhisperModel

        # faster-whisper handles its own GPU memory management
        model_info.model_obj = WhisperModel(
            model_info.path,
            device="cuda",
            compute_type="float16",
        )

    async def _load_indic_whisper(self, model_info: ModelInfo) -> None:
        """Load IndicWhisper model."""
        from faster_whisper import WhisperModel

        model_info.model_obj = WhisperModel(
            model_info.path,
            device="cuda",
            compute_type="float16",
        )

    async def _load_parler_tts(self, model_info: ModelInfo) -> None:
        """Load Indic-Parler-TTS model."""
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        model_info.model_obj = AutoModelForCausalLM.from_pretrained(
            model_info.path,
            torch_dtype=torch.float16,
            device_map="cuda",
            trust_remote_code=True,
        )
        model_info.processor = AutoTokenizer.from_pretrained(model_info.path)

    async def _unload_model(self, model_name: ModelName) -> None:
        """Unload a model from GPU and free VRAM."""
        model_info = self._models.get(model_name)
        if not model_info or not model_info.loaded:
            return

        logger.info(f"Unloading {model_name.value} from GPU...")

        # Delete model objects
        model_info.model_obj = None
        model_info.processor = None
        model_info.loaded = False

        # Force garbage collection and clear CUDA cache
        import gc

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()

        self._current_model = None
        logger.info(f"Unloaded {model_name.value}, VRAM freed")

    async def unload_all(self) -> None:
        """Unload all models from GPU."""
        async with self._lock:
            for model_name in list(self._models.keys()):
                if self._models[model_name].loaded:
                    await self._unload_model(model_name)

    @asynccontextmanager
    async def model_context(self, model_name: ModelName):
        """Context manager for temporary model loading.

        Usage:
            async with gpu_optimizer.model_context(ModelName.MEDGEMMA) as model_info:
                # model is loaded, use model_info.model_obj
                result = model_info.model_obj.generate(...)
            # model is unloaded on exit
        """
        model_info = await self.ensure_model_loaded(model_name)
        try:
            yield model_info
        finally:
            # Optionally unload after use - keep for now to avoid thrashing
            # await self._unload_model(model_name)
            pass

    def get_status(self) -> dict:
        """Get current GPU status."""
        return {
            "device": self._device,
            "vram_total_gb": round(self._vram_total_gb, 2),
            "vram_available_gb": round(self.vram_available_gb, 2),
            "current_model": self._current_model.value if self._current_model else None,
            "loaded_models": [m.name.value for m in self._models.values() if m.loaded],
        }


# Global instance
gpu_optimizer = GPUOptimizer()
