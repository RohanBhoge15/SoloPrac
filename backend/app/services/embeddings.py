"""Embedding Service — MedCPT, BGE-M3, BiomedCLIP pipelines with lazy loading + NIM API.

Heavy ML imports (torch, sentence-transformers, numpy, PIL) are deferred to
avoid torchvision C++ binding crashes at module import time. They are imported
lazily inside the methods that actually need them.
"""

import asyncio
import base64
import hashlib
import importlib.util
import logging
import os
from typing import Any, Dict, List, Literal, Optional

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


# ─── Lazy import helpers ───


def _get_torch():
    import torch

    return torch


def _get_numpy():
    import numpy

    return numpy


def _get_sentence_transformer():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer


def _get_pil_image():
    from PIL import Image

    return Image


def _default_device() -> str:
    """Return 'cuda' if a GPU is available, else 'cpu'."""
    try:
        torch = _get_torch()
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _module_available(name: str) -> bool:
    """True if an optional dependency can be imported (without importing it)."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


HAS_FLAG_EMBEDDING = _module_available("FlagEmbedding")
HAS_OPEN_CLIP = _module_available("open_clip")


class EmbeddingBackendUnavailable(RuntimeError):
    """Raised when the backend required for a modality is not installed."""


# ─── Model Config ───
EMBEDDING_MODELS: Dict[str, Dict[str, Any]] = {
    "medcpt": {
        "model_name": "ncbi/MedCPT-Query-Encoder",
        "dim": 768,
        "query_prefix": "",
        "passage_model": "ncbi/MedCPT-Article-Encoder",
    },
    "bge-m3": {
        "model_name": "BAAI/bge-m3",
        "dim": 1024,
        "supports_sparse": HAS_FLAG_EMBEDDING,
    },
    "biomedclip": {
        "model_name": "microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224",
        "open_clip_name": "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224",
        "dim": 512,
    },
}

ModelName = Literal["medcpt", "bge-m3", "biomedclip"]

_WEIGHT_MARKERS: Dict[str, tuple] = {
    "medcpt": ("model.safetensors", "pytorch_model.bin"),
    "bge-m3": ("model.safetensors", "pytorch_model.bin"),
    "biomedclip": ("open_clip_pytorch_model.bin",),
}


def _local_model_path(name: ModelName) -> str:
    """Resolve a model to its local /models directory when present."""
    path = {
        "medcpt": settings.MEDCPT_QUERY_PATH,
        "bge-m3": settings.BGE_M3_PATH,
        "biomedclip": settings.BIOMEDCLIP_PATH,
    }.get(name, "")
    if path and os.path.isdir(path):
        if any(os.path.exists(os.path.join(path, m)) for m in _WEIGHT_MARKERS[name]):
            return path
        logger.warning(
            "Local model dir %s is incomplete — falling back to %s",
            path,
            EMBEDDING_MODELS[name]["model_name"],
        )
    return EMBEDDING_MODELS[name]["model_name"]


class EmbeddingService:
    """Lazy-loaded embedding models with health checks, NIM API for BiomedCLIP,
    Redis caching, and GPU-aware loading."""

    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._loaded: Dict[str, bool] = {}
        self._nim_client: Optional[AsyncOpenAI] = None
        self._cache_client = None
        if settings.NIM_API_KEY:
            self._nim_client = AsyncOpenAI(
                api_key=settings.NIM_API_KEY,
                base_url=settings.NIM_BASE_URL,
            )

    async def _get_cache(self):
        if self._cache_client is not None:
            return self._cache_client
        try:
            from app.services.redis import redis_service

            self._cache_client = await redis_service.connect()
        except Exception:
            self._cache_client = False
        return self._cache_client

    def _cache_key(self, prefix: str, texts: List[str]) -> str:
        content = "|".join(texts)
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return f"emb:{prefix}:{h}"

    def _resolve_device(self, name: ModelName) -> str:
        """Pick the device for a model, downgrading to CPU if the GPU is full."""
        torch = _get_torch()
        device = _default_device()
        if device == "cuda":
            try:
                free_mem = torch.cuda.mem_get_info()[0] / (1024**3)
                if free_mem < 1.0:
                    logger.warning(
                        "GPU has only %.1fGB free — loading %s on CPU instead",
                        free_mem,
                        name,
                    )
                    device = "cpu"
            except Exception:
                pass
        return device

    def _load_model(self, name: ModelName) -> Any:
        """Lazy-load a specific model."""
        if name in self._models:
            return self._models[name]

        cfg = EMBEDDING_MODELS[name]
        device = self._resolve_device(name)

        logger.info("Loading embedding model: %s (%s) on %s", name, cfg["model_name"], device)

        if name == "bge-m3":
            model = self._load_bge_m3(cfg, device)
        elif name == "biomedclip":
            model = self._load_biomedclip(cfg, device)
        else:
            ST = _get_sentence_transformer()
            model = ST(_local_model_path("medcpt"), device=device)

        self._models[name] = model
        self._loaded[name] = True
        logger.info("Loaded %s successfully (dim=%s, device=%s)", name, cfg["dim"], device)
        return model

    def _load_bge_m3(self, cfg: Dict[str, Any], device: str) -> Any:
        """Load BGE-M3 via FlagEmbedding (dense + sparse) or ST (dense only)."""
        if HAS_FLAG_EMBEDDING:
            from FlagEmbedding import BGEM3FlagModel

            return BGEM3FlagModel(
                _local_model_path("bge-m3"),
                use_fp16=(device == "cuda"),
                devices=device,
            )
        logger.warning("FlagEmbedding not installed — loading BGE-M3 via sentence-transformers (dense only).")
        ST = _get_sentence_transformer()
        return ST(_local_model_path("bge-m3"), device=device)

    def _load_biomedclip(self, cfg: Dict[str, Any], device: str) -> Dict[str, Any]:
        """Load BiomedCLIP through open_clip."""
        if not HAS_OPEN_CLIP:
            raise EmbeddingBackendUnavailable("BiomedCLIP requires open_clip_torch. Image embedding unavailable.")
        import open_clip

        local = _local_model_path("biomedclip")
        if local != cfg["model_name"]:
            model_name = f"local-dir:{local}"
            pretrained = os.path.join(local, "open_clip_pytorch_model.bin")
        else:
            model_name = cfg["open_clip_name"]
            pretrained = None
        model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
        tokenizer = open_clip.get_tokenizer(model_name)
        torch = _get_torch()
        model = model.to(device).eval()
        return {"model": model, "preprocess": preprocess, "tokenizer": tokenizer, "device": device}

    def get_model(self, name: ModelName) -> Any:
        if name not in self._loaded or not self._loaded[name]:
            return self._load_model(name)
        return self._models[name]

    def is_loaded(self, name: ModelName) -> bool:
        return self._loaded.get(name, False)

    def supports_sparse(self) -> bool:
        return HAS_FLAG_EMBEDDING

    def supports_images(self) -> bool:
        return HAS_OPEN_CLIP

    # ─── Encoding methods ───

    async def encode_medcpt(self, texts: List[str], is_query: bool = True) -> List:
        numpy = _get_numpy()
        cache = await self._get_cache()
        cache_key = self._cache_key("medcpt", texts)
        if cache:
            try:
                cached = await cache.get(cache_key)
                if cached:
                    import json

                    return [numpy.array(v) for v in json.loads(cached)]
            except Exception:
                pass
        model = self.get_model("medcpt")
        result = await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)
        if cache:
            try:
                import json

                await cache.set(cache_key, json.dumps(result.tolist()), ex=3600)
            except Exception:
                pass
        return result

    @staticmethod
    def _lexical_weights_to_sparse(weights: Dict[str, float]) -> Dict[str, List]:
        indices: List[int] = []
        values: List[float] = []
        for token_id, weight in weights.items():
            try:
                indices.append(int(token_id))
            except (TypeError, ValueError):
                continue
            values.append(float(weight))
        return {"indices": indices, "values": values}

    async def encode_bge_m3(
        self,
        texts: List[str],
        return_dense: bool = True,
        return_sparse: bool = True,
    ) -> Dict[str, List]:
        cache = await self._get_cache()
        cache_key = self._cache_key("bge_m3", texts)
        if cache and return_dense and not return_sparse:
            try:
                cached = await cache.get(cache_key)
                if cached:
                    import json

                    return {"dense": json.loads(cached)}
            except Exception:
                pass
        model = self.get_model("bge-m3")
        result: Dict[str, List] = {}
        if HAS_FLAG_EMBEDDING:
            output = await asyncio.to_thread(
                model.encode,
                texts,
                return_dense=return_dense,
                return_sparse=return_sparse,
                return_colbert_vecs=False,
            )
            if return_dense:
                dense = output["dense_vecs"]
                result["dense"] = dense.tolist() if hasattr(dense, "tolist") else list(dense)
            if return_sparse:
                result["sparse"] = [self._lexical_weights_to_sparse(w) for w in output["lexical_weights"]]
        else:
            if return_dense:
                dense = await asyncio.to_thread(model.encode, texts, normalize_embeddings=True)
                result["dense"] = dense.tolist()
            if return_sparse:
                logger.warning("Sparse BGE-M3 vectors requested but FlagEmbedding not installed.")
        if cache and return_dense and not return_sparse:
            try:
                import json

                await cache.set(cache_key, json.dumps(result["dense"]), ex=3600)
            except Exception:
                pass
        return result

    def _clip_encode_images(self, bundle, images) -> "np.ndarray":
        torch = _get_torch()
        batch = torch.stack([bundle["preprocess"](img) for img in images]).to(bundle["device"])
        with torch.no_grad():
            feats = bundle["model"].encode_image(batch)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.cpu().numpy()

    def _clip_encode_texts(self, bundle, texts) -> "np.ndarray":
        torch = _get_torch()
        tokens = bundle["tokenizer"](texts).to(bundle["device"])
        with torch.no_grad():
            feats = bundle["model"].encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.cpu().numpy()

    async def encode_biomedclip_image(self, image_path: str) -> List[float]:
        Image = _get_pil_image()
        bundle = self.get_model("biomedclip")
        image = Image.open(image_path).convert("RGB")
        result = await asyncio.to_thread(self._clip_encode_images, bundle, [image])
        return result[0].tolist()

    async def encode_biomedclip_images(self, image_paths: List[str]) -> List[List[float]]:
        Image = _get_pil_image()
        bundle = self.get_model("biomedclip")
        images = [Image.open(p).convert("RGB") for p in image_paths]
        result = await asyncio.to_thread(self._clip_encode_images, bundle, images)
        return result.tolist()

    async def encode_biomedclip_text(self, text: str) -> List[float]:
        bundle = self.get_model("biomedclip")
        result = await asyncio.to_thread(self._clip_encode_texts, bundle, [text])
        return result[0].tolist()

    async def encode_biomedclip_texts(self, texts: List[str]) -> List[List[float]]:
        bundle = self.get_model("biomedclip")
        result = await asyncio.to_thread(self._clip_encode_texts, bundle, texts)
        return result.tolist()

    async def encode_single(self, name: ModelName, text: str):
        numpy = _get_numpy()
        if name == "biomedclip":
            bundle = self.get_model("biomedclip")
            return await asyncio.to_thread(self._clip_encode_texts, bundle, [text])
        if name == "bge-m3" and HAS_FLAG_EMBEDDING:
            model = self.get_model("bge-m3")
            output = await asyncio.to_thread(
                model.encode,
                [text],
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            return numpy.asarray(output["dense_vecs"])
        model = self.get_model(name)
        return await asyncio.to_thread(model.encode, [text], normalize_embeddings=True)

    # ─── NIM fallback ───

    async def encode_biomedclip_nim(
        self,
        image_paths: Optional[List[str]] = None,
        texts: Optional[List[str]] = None,
    ) -> Dict[str, List]:
        if self._nim_client is None:
            logger.error("NIM client not configured — NIM_API_KEY required")
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
