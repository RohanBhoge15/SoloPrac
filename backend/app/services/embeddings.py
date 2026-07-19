"""Embedding Service — MedCPT, BGE-M3, NV-CLIP pipelines with lazy loading."""

import os
import asyncio
from typing import List, Dict, Optional, Literal
from functools import lru_cache
import logging

import numpy as np
from sentence_transformers import SentenceTransformer
import torch

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Model Config ───
EMBEDDING_MODELS = {
    "medcpt": {
        "model_name": "ncbi/MedCPT-Query-Encoder",
        "dim": 768,
        "device": "cpu",  # small enough for CPU
        "query_prefix": "",
        "passage_model": "ncbi/MedCPT-Article-Encoder",
    },
    "bge-m3": {
        "model_name": "BAAI/bge-m3",
        "dim": 1024,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "supports_sparse": True,
    },
    "nvclip": {
        "model_name": "nvidia/NV-CLIP",
        "dim": 512,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "is_multimodal": True,
    },
}

ModelName = Literal["medcpt", "bge-m3", "nvclip"]


class EmbeddingService:
    """Lazy-loaded embedding models with health checks."""

    def __init__(self):
        self._models: Dict[str, SentenceTransformer] = {}
        self._loaded: Dict[str, bool] = {}

    def _load_model(self, name: ModelName) -> SentenceTransformer:
        """Lazy-load a specific model."""
        if name in self._models:
            return self._models[name]

        cfg = EMBEDDING_MODELS[name]
        logger.info(f"Loading embedding model: {name} ({cfg['model_name']}) on {cfg['device']}")

        # Force CPU for large models on RTX 3050 to avoid OOM
        device = cfg["device"]
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning(f"CUDA not available, falling back to CPU for {name}")
            device = "cpu"

        model = SentenceTransformer(cfg["model_name"], device=device)
        self._models[name] = model
        self._loaded[name] = True
        logger.info(f"Loaded {name} successfully (dim={cfg['dim']})")
        return model

    def get_model(self, name: ModelName) -> SentenceTransformer:
        if name not in self._loaded or not self._loaded[name]:
            return self._load_model(name)
        return self._models[name]

    def is_loaded(self, name: ModelName) -> bool:
        return self._loaded.get(name, False)

    # ─── Encoding ───

    async def encode_medcpt(self, texts: List[str], is_query: bool = True) -> List[np.ndarray]:
        """Encode clinical text with MedCPT (asymmetric query/passage)."""
        model = self.get_model("medcpt")
        # MedCPT uses asymmetric encoders - we'd need both query and passage
        # For now, use query encoder for both
        return await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)

    async def encode_bge_m3(self, texts: List[str], return_dense: bool = True, return_sparse: bool = True) -> Dict[str, List]:
        """Encode with BGE-M3 — dense + sparse + multi-vector."""
        model = self.get_model("bge-m3")
        result = {}

        if return_dense:
            dense = await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)
            result["dense"] = dense.tolist()

        if return_sparse:
            # BGE-M3 sparse: use model's sparse encoder
            sparse = await asyncio.to_thread(model.encode, texts, return_sparse=True)
            result["sparse"] = sparse["sparse_embedding"] if isinstance(sparse, dict) else sparse

        return result

    async def encode_nvclip(self, images: List[str] = None, texts: List[str] = None) -> Dict[str, List]:
        """Encode images and/or text with NV-CLIP."""
        model = self.get_model("nvclip")
        result = {}

        if images:
            img_emb = await asyncio.to_thread(model.encode, images)
            result["image"] = img_emb.tolist()

        if texts:
            txt_emb = await asyncio.to_thread(model.encode, texts)
            result["text"] = txt_emb.tolist()

        return result

    async def encode_single(self, name: ModelName, text: str) -> np.ndarray:
        model = self.get_model(name)
        return await asyncio.to_thread(model.encode, [text], normalize_embeddings=True)

    # ─── Health ───

    def is_healthy(self) -> bool:
        try:
            # Test that at least one model loads
            self.get_model("medcpt")
            return True
        except Exception as e:
            logger.error(f"Embedding health check failed: {e}")
            return False


# Global instance
embedding_service = EmbeddingService()