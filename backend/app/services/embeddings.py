"""Embedding Service — MedCPT, BGE-M3, NV-CLIP pipelines with lazy loading + NIM API."""

import os
import asyncio
import base64
from typing import List, Dict, Optional, Literal
from functools import lru_cache
import logging

import numpy as np
from sentence_transformers import SentenceTransformer
import torch
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Model Config ───
EMBEDDING_MODELS = {
    "medcpt": {
        "model_name": "ncbi/MedCPT-Query-Encoder",
        "dim": 768,
        "device": "cpu",
        "query_prefix": "",
        "passage_model": "ncbi/MedCPT-Article-Encoder",
    },
    "bge-m3": {
        "model_name": "BAAI/bge-m3",
        "dim": 1024,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "supports_sparse": True,
    },
}

ModelName = Literal["medcpt", "bge-m3"]


class EmbeddingService:
    """Lazy-loaded embedding models with health checks + NIM API for NV-CLIP."""

    def __init__(self):
        self._models: Dict[str, SentenceTransformer] = {}
        self._loaded: Dict[str, bool] = {}
        self._nim_client: Optional[AsyncOpenAI] = None
        if settings.NIM_API_KEY:
            self._nim_client = AsyncOpenAI(
                api_key=settings.NIM_API_KEY,
                base_url=settings.NIM_BASE_URL,
            )

    def _load_model(self, name: ModelName) -> SentenceTransformer:
        """Lazy-load a specific model."""
        if name in self._models:
            return self._models[name]

        cfg = EMBEDDING_MODELS[name]
        logger.info("Loading embedding model: %s (%s) on %s", name, cfg["model_name"], cfg["device"])

        device = cfg["device"]
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA not available, falling back to CPU for %s", name)
            device = "cpu"

        model = SentenceTransformer(cfg["model_name"], device=device)
        self._models[name] = model
        self._loaded[name] = True
        logger.info("Loaded %s successfully (dim=%s)", name, cfg["dim"])
        return model

    def get_model(self, name: ModelName) -> SentenceTransformer:
        if name not in self._loaded or not self._loaded[name]:
            return self._load_model(name)
        return self._models[name]

    def is_loaded(self, name: ModelName) -> bool:
        return self._loaded.get(name, False)

    # ─── Local Encoding (MedCPT + BGE-M3) ───

    async def encode_medcpt(self, texts: List[str], is_query: bool = True) -> List[np.ndarray]:
        """Encode clinical text with MedCPT."""
        model = self.get_model("medcpt")
        return await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)

    async def encode_bge_m3(
        self, texts: List[str],
        return_dense: bool = True,
        return_sparse: bool = True,
    ) -> Dict[str, List]:
        """Encode with BGE-M3 — dense + sparse."""
        model = self.get_model("bge-m3")
        result = {}

        if return_dense:
            dense = await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)
            result["dense"] = dense.tolist()
        if return_sparse:
            sparse = await asyncio.to_thread(model.encode, texts, return_sparse=True)
            result["sparse"] = sparse["sparse_embedding"] if isinstance(sparse, dict) else sparse

        return result

    async def encode_single(self, name: ModelName, text: str) -> np.ndarray:
        model = self.get_model(name)
        return await asyncio.to_thread(model.encode, [text], normalize_embeddings=True)

    # ─── NV-CLIP via NIM API ───

    async def encode_nvclip_nim(
        self,
        image_paths: Optional[List[str]] = None,
        texts: Optional[List[str]] = None,
    ) -> Dict[str, List]:
        """Encode images and/or text using NV-CLIP via NVIDIA NIM API.

        Uses the NIM embeddings API endpoint, not a local model load.
        NV-CLIP is too large (12B params) to load on RTX 3050 alongside BGE-M3.

        Args:
            image_paths: List of paths to image files.
            texts: List of text strings to encode.

        Returns:
            {"image": List[List[float]], "text": List[List[float]]}
            Only includes keys for provided inputs.
        """
        if self._nim_client is None:
            logger.error("NIM client not configured — NV-CLIP requires NIM_API_KEY in .env")
            return {}

        result = {}

        if image_paths:
            image_embeddings = []
            for img_path in image_paths:
                try:
                    # Read and base64-encode the image
                    with open(img_path, "rb") as f:
                        img_b64 = base64.b64encode(f.read()).decode("utf-8")

                    response = await self._nim_client.embeddings.create(
                        model=settings.NVCLIP_MODEL,
                        input=[{"image": img_b64}],
                    )
                    emb = response.data[0].embedding if response.data else []
                    image_embeddings.append(emb)
                except Exception as exc:
                    logger.error("NV-CLIP image encoding failed for %s: %s", img_path, exc)
                    image_embeddings.append([])
            result["image"] = image_embeddings

        if texts:
            try:
                response = await self._nim_client.embeddings.create(
                    model=settings.NVCLIP_MODEL,
                    input=texts,
                )
                result["text"] = [d.embedding for d in response.data]
            except Exception as exc:
                logger.error("NV-CLIP text encoding failed: %s", exc)
                result["text"] = []

        return result

    async def encode_nvclip_image(self, image_path: str) -> List[float]:
        """Convenience: encode a single image and return its embedding vector."""
        result = await self.encode_nvclip_nim(image_paths=[image_path])
        return result.get("image", [[]])[0]

    async def encode_nvclip_text(self, text: str) -> List[float]:
        """Convenience: encode a single text query and return its embedding vector."""
        result = await self.encode_nvclip_nim(texts=[text])
        return result.get("text", [[]])[0]

    # ─── Fallback: local NV-CLIP (if model is cached) ───
    # Kept for environments where NIM is unreachable

    async def encode_nvclip_local(self, images: List[str] = None, texts: List[str] = None) -> Dict[str, List]:
        """Fallback: encode using locally loaded NV-CLIP (requires 12GB VRAM)."""
        try:
            from sentence_transformers import SentenceTransformer as ST
            model = ST("nvidia/NV-CLIP", device="cpu")
            result = {}
            if images:
                img_emb = await asyncio.to_thread(model.encode, images)
                result["image"] = img_emb.tolist()
            if texts:
                txt_emb = await asyncio.to_thread(model.encode, texts)
                result["text"] = txt_emb.tolist()
            return result
        except Exception as exc:
            logger.error("Local NV-CLIP encoding failed: %s", exc)
            return {}

    # ─── Health ───

    def is_healthy(self) -> bool:
        try:
            self.get_model("medcpt")
            return True
        except Exception as e:
            logger.error("Embedding health check failed: %s", e)
            return False


# Global instance
embedding_service = EmbeddingService()