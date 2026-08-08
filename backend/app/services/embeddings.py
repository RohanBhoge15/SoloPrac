"""Embedding Service — MedCPT, BGE-M3, BiomedCLIP pipelines with lazy loading + NIM API.

Includes Redis-backed caching for repeated queries and GPU-aware model loading.

Backends per model:
  - medcpt     — sentence-transformers (dense only; that is all MedCPT provides)
  - bge-m3     — FlagEmbedding.BGEM3FlagModel when installed (the only loader that
                 returns real sparse/lexical weights). Without FlagEmbedding we
                 fall back to sentence-transformers for DENSE ONLY and warn; the
                 sparse modality is then reported as unavailable, never faked.
  - biomedclip — open_clip (the model is an OpenCLIP checkpoint and cannot be
                 loaded by plain sentence-transformers). Without open_clip the
                 image modality is unavailable and callers get a clear error.

Nothing in this module ever returns zero vectors or synthetic embeddings as a
stand-in for a missing backend: callers get None/raise so degraded retrieval is
visible rather than silent.
"""

import asyncio
import base64
import hashlib
import importlib.util
import logging
import os
from typing import Any, Dict, List, Literal, Optional

import numpy as np
import torch
from openai import AsyncOpenAI
from PIL import Image
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger(__name__)


def _module_available(name: str) -> bool:
    """True if an optional dependency can be imported (without importing it)."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


HAS_FLAG_EMBEDDING = _module_available("FlagEmbedding")
HAS_OPEN_CLIP = _module_available("open_clip")


class EmbeddingBackendUnavailable(RuntimeError):
    """Raised when the backend required for a modality is not installed.

    Deliberately loud: an unavailable modality must never be papered over with
    zero vectors, which would silently poison retrieval.
    """


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
        # Sparse (lexical weight) output only exists via FlagEmbedding's loader.
        "supports_sparse": HAS_FLAG_EMBEDDING,
    },
    "biomedclip": {
        "model_name": "microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224",
        # open_clip resolves the checkpoint straight off the HF hub
        "open_clip_name": "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224",
        "dim": 512,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
    },
}

ModelName = Literal["medcpt", "bge-m3", "biomedclip"]

# A model directory is only usable if it contains the actual weight file; a
# partial download (configs/tokenizer only) must not be treated as available.
_WEIGHT_MARKERS: Dict[ModelName, tuple] = {
    "medcpt": ("model.safetensors", "pytorch_model.bin"),
    "bge-m3": ("model.safetensors", "pytorch_model.bin"),
    "biomedclip": ("open_clip_pytorch_model.bin",),
}


def _local_model_path(name: ModelName) -> str:
    """Resolve a model to its local /models directory when present, else the HF name.

    Prevents re-downloading embedder weights into HF_HOME when a local copy
    already exists (mounted from the host models cache). Falls back to the
    Hugging Face repo id if the directory is missing or incomplete, so the
    service still works without the mount.
    """
    path = {
        "medcpt": settings.MEDCPT_QUERY_PATH,
        "bge-m3": settings.BGE_M3_PATH,
        "biomedclip": settings.BIOMEDCLIP_PATH,
    }.get(name, "")
    if path and os.path.isdir(path):
        if any(os.path.exists(os.path.join(path, m)) for m in _WEIGHT_MARKERS[name]):
            return path
        logger.warning(
            "Local model dir %s is incomplete (missing weight file) — " "falling back to %s",
            path,
            EMBEDDING_MODELS[name]["model_name"],
        )
    return EMBEDDING_MODELS[name]["model_name"]


class EmbeddingService:
    """Lazy-loaded embedding models with health checks, NIM API for BiomedCLIP,
    Redis caching, and GPU-aware loading."""

    def __init__(self):
        # Values are backend-specific: SentenceTransformer, BGEM3FlagModel, or
        # the open_clip (model, preprocess, tokenizer) bundle.
        self._models: Dict[str, Any] = {}
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

    def _resolve_device(self, name: ModelName) -> str:
        """Pick the device for a model, downgrading to CPU if the GPU is full."""
        device = EMBEDDING_MODELS[name]["device"]
        if device == "cuda":
            try:
                free_mem = torch.cuda.mem_get_info()[0] / (1024**3)  # GB
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
        """Lazy-load a specific model with the loader that model actually needs."""
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
            model = SentenceTransformer(_local_model_path("medcpt"), device=device)

        self._models[name] = model
        self._loaded[name] = True
        logger.info("Loaded %s successfully (dim=%s, device=%s)", name, cfg["dim"], device)
        return model

    def _load_bge_m3(self, cfg: Dict[str, Any], device: str) -> Any:
        """Load BGE-M3 via FlagEmbedding (dense + sparse) or ST (dense only).

        BGEM3FlagModel.encode() genuinely returns ``dense_vecs`` and
        ``lexical_weights``; SentenceTransformer.encode() has no sparse output at
        all, so with only sentence-transformers installed we degrade to dense and
        say so out loud.
        """
        if HAS_FLAG_EMBEDDING:
            from FlagEmbedding import BGEM3FlagModel

            return BGEM3FlagModel(
                _local_model_path("bge-m3"),
                use_fp16=(device == "cuda"),
                devices=device,
            )

        logger.warning(
            "FlagEmbedding is not installed — loading BAAI/bge-m3 through "
            "sentence-transformers for DENSE vectors only. Sparse/lexical "
            "retrieval is UNAVAILABLE (hybrid search degrades to dense-only). "
            "Install `FlagEmbedding` to enable sparse vectors."
        )
        return SentenceTransformer(_local_model_path("bge-m3"), device=device)

    def _load_biomedclip(self, cfg: Dict[str, Any], device: str) -> Dict[str, Any]:
        """Load BiomedCLIP through open_clip.

        BiomedCLIP is an OpenCLIP checkpoint (PubMedBERT text tower + ViT image
        tower); plain SentenceTransformer cannot load it, and never could — it
        has no image tower and no way to encode a PIL.Image.
        """
        if not HAS_OPEN_CLIP:
            raise EmbeddingBackendUnavailable(
                "BiomedCLIP requires the `open_clip_torch` package, which is not "
                "installed. The image modality is unavailable: image embedding "
                "and image search will fail until open_clip is installed, or "
                "until NIM_API_KEY is configured to use encode_biomedclip_nim()."
            )

        import open_clip

        local = _local_model_path("biomedclip")
        if local != cfg["model_name"]:
            # Load straight from the local /models checkpoint (OpenCLIP format):
            # the `local-dir:` schema reads open_clip_config.json + weights from
            # disk, so nothing is re-downloaded into HF_HOME.
            model_name = f"local-dir:{local}"
            pretrained = os.path.join(local, "open_clip_pytorch_model.bin")
        else:
            model_name = cfg["open_clip_name"]
            pretrained = None
        model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
        tokenizer = open_clip.get_tokenizer(model_name)
        model = model.to(device).eval()
        return {
            "model": model,
            "preprocess": preprocess,
            "tokenizer": tokenizer,
            "device": device,
        }

    def get_model(self, name: ModelName) -> Any:
        if name not in self._loaded or not self._loaded[name]:
            return self._load_model(name)
        return self._models[name]

    def is_loaded(self, name: ModelName) -> bool:
        return self._loaded.get(name, False)

    def supports_sparse(self) -> bool:
        """Whether real BGE-M3 sparse vectors can be produced in this process."""
        return HAS_FLAG_EMBEDDING

    def supports_images(self) -> bool:
        """Whether local BiomedCLIP image embedding is available."""
        return HAS_OPEN_CLIP

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

    @staticmethod
    def _lexical_weights_to_sparse(weights: Dict[str, float]) -> Dict[str, List]:
        """Convert BGE-M3 lexical weights ({token_id: weight}) to indices/values."""
        indices: List[int] = []
        values: List[float] = []
        for token_id, weight in weights.items():
            try:
                indices.append(int(token_id))
            except (TypeError, ValueError):
                # Non-numeric key: not a token id, cannot be used as a sparse index
                continue
            values.append(float(weight))
        return {"indices": indices, "values": values}

    async def encode_bge_m3(
        self,
        texts: List[str],
        return_dense: bool = True,
        return_sparse: bool = True,
    ) -> Dict[str, List]:
        """Encode with BGE-M3 — dense + sparse. Dense results cached.

        Returns:
            {"dense": [[float, ...], ...],
             "sparse": [{"indices": [int, ...], "values": [float, ...]}, ...]}

            ``sparse`` is present only when sparse vectors were requested AND
            FlagEmbedding is installed. When it is not installed the key is
            omitted entirely (with a warning) rather than filled with zeros, so
            callers can tell that lexical retrieval is off.
        """
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
        result: Dict[str, List] = {}

        if HAS_FLAG_EMBEDDING:
            # BGEM3FlagModel encodes dense + sparse in a single forward pass.
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
                # No sparse backend — say so; do NOT return empty/zero vectors
                # dressed up as sparse embeddings.
                logger.warning(
                    "Sparse BGE-M3 vectors requested but FlagEmbedding is not "
                    "installed — returning dense only; hybrid search is "
                    "dense-only for this call."
                )

        # Cache dense results for 1 hour
        if cache and return_dense and not return_sparse:
            try:
                import json

                await cache.set(cache_key, json.dumps(result["dense"]), ex=3600)
            except Exception:
                pass

        return result

    # ─── BiomedCLIP (open_clip) ───

    def _clip_encode_images(self, bundle: Dict[str, Any], images: List[Image.Image]) -> np.ndarray:
        """Blocking BiomedCLIP image forward pass; returns L2-normalized vectors."""
        batch = torch.stack([bundle["preprocess"](img) for img in images]).to(bundle["device"])
        with torch.no_grad():
            feats = bundle["model"].encode_image(batch)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.cpu().numpy()

    def _clip_encode_texts(self, bundle: Dict[str, Any], texts: List[str]) -> np.ndarray:
        """Blocking BiomedCLIP text forward pass; returns L2-normalized vectors."""
        tokens = bundle["tokenizer"](texts).to(bundle["device"])
        with torch.no_grad():
            feats = bundle["model"].encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.cpu().numpy()

    async def encode_biomedclip_image(self, image_path: str) -> List[float]:
        """Encode a single image using BiomedCLIP (local open_clip model).

        Raises:
            EmbeddingBackendUnavailable: if open_clip is not installed.
        """
        bundle = self.get_model("biomedclip")
        image = Image.open(image_path).convert("RGB")
        result = await asyncio.to_thread(self._clip_encode_images, bundle, [image])
        return result[0].tolist()

    async def encode_biomedclip_images(self, image_paths: List[str]) -> List[List[float]]:
        """Encode multiple images using BiomedCLIP (local open_clip model)."""
        bundle = self.get_model("biomedclip")
        images = [Image.open(p).convert("RGB") for p in image_paths]
        result = await asyncio.to_thread(self._clip_encode_images, bundle, images)
        return result.tolist()

    async def encode_biomedclip_text(self, text: str) -> List[float]:
        """Encode text using BiomedCLIP (local open_clip model)."""
        bundle = self.get_model("biomedclip")
        result = await asyncio.to_thread(self._clip_encode_texts, bundle, [text])
        return result[0].tolist()

    async def encode_biomedclip_texts(self, texts: List[str]) -> List[List[float]]:
        """Encode multiple texts using BiomedCLIP (local open_clip model)."""
        bundle = self.get_model("biomedclip")
        result = await asyncio.to_thread(self._clip_encode_texts, bundle, texts)
        return result.tolist()

    async def encode_single(self, name: ModelName, text: str) -> np.ndarray:
        """Encode one text with the named model (dense vectors, shape (1, dim))."""
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
            return np.asarray(output["dense_vecs"])
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
