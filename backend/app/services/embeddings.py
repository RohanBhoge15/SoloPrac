"""Embedding Service — MedCPT, BGE-M3, BiomedCLIP pipelines with lazy loading + NIM API.

Includes Redis-backed caching for repeated queries and GPU-aware model loading.
"""

import os
import asyncio
import hashlib
import base64
from typing import List, Dict, Optional, Literal
from functools import lru_cache
import logging

import numpy as np
from sentence_transformers import SentenceTransformer
import torch
from openai import AsyncOpenAI
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Model Config ───
EMBEDDING_MODELS = {
    "medcpt": {
        "model_name": "ncbi/MedCPT-Query-Encoder",
        "dim": 768,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "query_prefix": "",
        "passage_model": "ncbi/MedCPT-Article-Encoder",
    },
    "bge-m3": {
        "model_name": "BAAI/bge-m3",
        "dim": 1024,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "supports_sparse": True,
    },
    "biomedclip": {
        "model_name": "microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224",
        "dim": 512,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
    },
}

ModelName = Literal["medcpt", "bge-m3", "biomedclip"]


class EmbeddingService:
    """Lazy-loaded embedding models with health checks, NIM API for BiomedCLIP,
    Redis caching, and GPU-aware loading."""

    def __init__(self):
        self._models: Dict[str, SentenceTransformer] = {}
        self._loaded: Dict[str, bool] = {}
        self._nim_client: Optional[AsyncOpenAI] = None
        self._cache_client = None  # Redis cache, lazy-loaded
        if settings.NIM_API_KEY:
            self._nim_client = AsyncOpenAI(
                api_key=settings.NIM_API_KEY,
                base_url=settings.NIM_BASE_URL,
            )

    async def _get_cache(self):
        """Lazy-load Redis cache client."""
        if self._cache_client is not None:
            return self._cache_client
        try:
            from app.services.redis import redis_service
            self._cache_client = await redis_service.connect()
        except Exception:
            self._cache_client = False  # Mark as unavailable
        return self._cache_client

    def _cache_key(self, prefix: str, texts: List[str]) -> str:
        """Generate a content-hash cache key for a list of texts."""
        content = "|".join(texts)
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return f"emb:{prefix}:{h}"

    def _load_model(self, name: ModelName) -> SentenceTransformer:
        """Lazy-load a specific model on the best available device."""
        if name in self._models:
            return self._models[name]

        cfg = EMBEDDING_MODELS[name]
        device = cfg["device"]

        # Check GPU memory availability before loading on CUDA
        if device == "cuda":
            try:
                free_mem = torch.cuda.mem_get_info()[0] / (1024 ** 3)  # GB
                if free_mem < 1.0:
                    logger.warning(
                        "GPU has only %.1fGB free — loading %s on CPU instead",
                        free_mem, name,
                    )
                    device = "cpu"
            except Exception:
                pass

        logger.info("Loading embedding model: %s (%s) on %s", name, cfg["model_name"], device)

        model = SentenceTransformer(cfg["model_name"], device=device)
        self._models[name] = model
        self._loaded[name] = True
        logger.info("Loaded %s successfully (dim=%s, device=%s)", name, cfg["dim"], device)
        return model

    def get_model(self, name: ModelName) -> SentenceTransformer:
        if name not in self._loaded or not self._loaded[name]:
            return self._load_model(name)
        return self._models[name]

    def is_loaded(self, name: ModelName) -> bool:
        return self._loaded.get(name, False)

    # ─── Local Encoding (MedCPT + BGE-M3 + BiomedCLIP) ───

    async def encode_medcpt(self, texts: List[str], is_query: bool = True) -> List[np.ndarray]:
        """Encode clinical text with MedCPT. Results cached in Redis."""
        # Check cache first
        cache = await self._get_cache()
        cache_key = self._cache_key("medcpt", texts)
        if cache:
            try:
                cached = await cache.get(cache_key)
                if cached:
                    import json
                    return [np.array(v) for v in json.loads(cached)]
            except Exception:
                pass

        model = self.get_model("medcpt")
        result = await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)

        # Cache for 1 hour
        if cache:
            try:
                import json
                await cache.set(cache_key, json.dumps(result.tolist()), ex=3600)
            except Exception:
                pass

        return result

    async def encode_bge_m3(
        self, texts: List[str],
        return_dense: bool = True,
        return_sparse: bool = True,
    ) -> Dict[str, List]:
        """Encode with BGE-M3 — dense + sparse. Dense results cached."""
        cache = await self._get_cache()
        cache_key = self._cache_key("bge_m3", texts)

        # Check cache for dense results
        if cache and return_dense and not return_sparse:
            try:
                cached = await cache.get(cache_key)
                if cached:
                    import json
                    return {"dense": json.loads(cached)}
            except Exception:
                pass

        model = self.get_model("bge-m3")
        result = {}

        if return_dense:
            dense = await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)
            result["dense"] = dense.tolist()
        if return_sparse:
            sparse = await asyncio.to_thread(model.encode, texts, return_sparse=True)
            result["sparse"] = sparse["sparse_embedding"] if isinstance(sparse, dict) else sparse

        # Cache dense results for 1 hour
        if cache and return_dense and not return_sparse:
            try:
                import json
                await cache.set(cache_key, json.dumps(result["dense"]), ex=3600)
            except Exception:
                pass

        return result

    async def encode_biomedclip_image(self, image_path: str) -> List[float]:
        """Encode a single image using BiomedCLIP (local model)."""
        model = self.get_model("biomedclip")
        image = Image.open(image_path).convert("RGB")
        result = await asyncio.to_thread(model.encode, [image], normalize_embeddings=True)
        return result[0].tolist()

    async def encode_biomedclip_images(self, image_paths: List[str]) -> List[List[float]]:
        """Encode multiple images using BiomedCLIP (local model)."""
        model = self.get_model("biomedclip")
        images = [Image.open(p).convert("RGB") for p in image_paths]
        result = await asyncio.to_thread(model.encode, images, normalize_embeddings=True)
        return result.tolist()

    async def encode_biomedclip_text(self, text: str) -> List[float]:
        """Encode text using BiomedCLIP (local model)."""
        model = self.get_model("biomedclip")
        result = await asyncio.to_thread(model.encode, [text], normalize_embeddings=True)
        return result[0].tolist()

    async def encode_biomedclip_texts(self, texts: List[str]) -> List[List[float]]:
        """Encode multiple texts using BiomedCLIP (local model)."""
        model = self.get_model("biomedclip")
        result = await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)
        return result.tolist()

    async def encode_single(self, name: ModelName, text: str) -> np.ndarray:
        model = self.get_model(name)
        return await asyncio.to_thread(model.encode, [text], normalize_embeddings=True)

    # ─── BiomedCLIP via NIM API (optional fallback) ───

    async def encode_biomedclip_nim(
        self,
        image_paths: Optional[List[str]] = None,
        texts: Optional[List[str]] = None,
    ) -> Dict[str, List]:
        """Encode images and/or text using BiomedCLIP via NVIDIA NIM API.

        Uses the NIM embeddings API endpoint. BiomedCLIP is small enough to run locally,
        but this provides a fallback if the local model isn't available.

        Args:
            image_paths: List of paths to image files.
            texts: List of text strings to encode.

        Returns:
            {"image": List[List[float]], "text": List[List[float]]}
            Only includes keys for provided inputs.
        """
        if self._nim_client is None:
            logger.error("NIM client not configured — BiomedCLIP requires NIM_API_KEY in .env")
            return {}

        result = {}

        if image_paths:
            image_embeddings = []
            for img_path in image_paths:
                try:
                    with open(img_path, "rb") as f:
                        img_b64 = base64.b64encode(f.read()).decode("utf-8")

                    response = await self._nim_client.embeddings.create(
                        model=settings.BIOMEDCLIP_MODEL,
                        input=[{"image": img_b64}],
                    )
                    emb = response.data[0].embedding if response.data else []
                    image_embeddings.append(emb)
                except Exception as exc:
                    logger.error("BiomedCLIP image encoding failed for %s: %s", img_path, exc)
                    image_embeddings.append([])
            result["image"] = image_embeddings

        if texts:
            try:
                response = await self._nim_client.embeddings.create(
                    model=settings.BIOMEDCLIP_MODEL,
                    input=texts,
                )
                result["text"] = [d.embedding for d in response.data]
            except Exception as exc:
                logger.error("BiomedCLIP text encoding failed: %s", exc)
                result["text"] = []

        return result

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