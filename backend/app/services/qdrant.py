"""Qdrant Vector Store Service — named vectors, hybrid search, payload filtering."""

import os
import json
import uuid
import asyncio
import logging
from typing import List, Dict, Any, Optional, Literal
from contextlib import asynccontextmanager

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition,
    Range, MatchValue, SearchRequest, SearchParams, UpdateStatus,
    PayloadSchemaType, SparseVectorParams, SparseVector,
    NamedVector, ScoredPoint,
)

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Projector (Feature C) ───
# Lazy import to avoid circular dependency
_projector_matrix: Optional[np.ndarray] = None


def _get_projector() -> Optional[np.ndarray]:
    """Get cached projector matrix (W: 512→1024) for BiomedCLIP → BGE-M3 projection."""
    global _projector_matrix
    if _projector_matrix is not None:
        return _projector_matrix
    try:
        from app.services.feature_c_projector import load_projector
        _projector_matrix = load_projector()
        return _projector_matrix
    except Exception:
        return None


# ─── Collection Config ───
PATIENT_VERSION_COLLECTION = "patient_versions"

VECTOR_CONFIG = {
    "medical_text": {"size": 768, "distance": Distance.COSINE},    # MedCPT
    "hybrid": {"size": 1024, "distance": Distance.COSINE},         # BGE-M3 dense
    "image": {"size": 512, "distance": Distance.COSINE},           # BiomedCLIP
}

SPARSE_VECTOR_NAME = "sparse"


class QdrantService:
    """Qdrant vector store for patient versions with hybrid multimodal search."""

    def __init__(self):
        self._client: Optional[QdrantClient] = None

    async def connect(self) -> QdrantClient:
        if self._client is not None:
            return self._client

        def _create_client():
            return QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                timeout=10,
            )

        self._client = await asyncio.to_thread(_create_client)
        # Test connection
        await asyncio.to_thread(self._client.get_collections)
        await self._ensure_collection()
        return self._client

    async def _ensure_collection(self):
        """Create collection with named vectors if it doesn't exist."""
        client = await self.connect()
        collections = await asyncio.to_thread(client.get_collections)
        names = [c.name for c in collections.collections]

        if PATIENT_VERSION_COLLECTION not in names:
            logger.info(f"Creating collection: {PATIENT_VERSION_COLLECTION}")
            await asyncio.to_thread(
                client.create_collection,
                collection_name=PATIENT_VERSION_COLLECTION,
                vectors_config={
                    "medical_text": VectorParams(size=768, distance=Distance.COSINE),
                    "hybrid": VectorParams(size=1024, distance=Distance.COSINE),
                    "image": VectorParams(size=512, distance=Distance.COSINE),
                },
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: SparseVectorParams(),
                },
                on_disk_payload=True,
            )
            # Create payload indexes for filtering
            for field_name, field_schema in [
                ("patient_id", PayloadSchemaType.KEYWORD),
                ("doctor_id", PayloadSchemaType.KEYWORD),
                ("timestamp", PayloadSchemaType.DATETIME),
                ("modality", PayloadSchemaType.KEYWORD),
                ("version_number", PayloadSchemaType.INTEGER),
                ("clinical_significance", PayloadSchemaType.FLOAT),
            ]:
                await asyncio.to_thread(
                    client.create_payload_index,
                    collection_name=PATIENT_VERSION_COLLECTION,
                    field_name=field_name,
                    field_schema=field_schema,
                )

    # ─── Point Operations ───

    async def upsert_version(self, version_data: Dict[str, Any]) -> str:
        """Upsert a patient version point with all vector representations."""
        client = await self.connect()

        # Generate point ID (use version_id if available, else generate)
        point_id = str(version_data.get("version_id", uuid.uuid4()))

        # Build point
        point = PointStruct(
            id=point_id,
            vector={
                "medical_text": version_data.get("medical_text_embedding", []),
                "hybrid": version_data.get("hybrid_embedding", []),
                "image": version_data.get("image_embedding", []),
            },
            sparse_vector={
                SPARSE_VECTOR_NAME: SparseVector(
                    indices=version_data.get("sparse_indices", []),
                    values=version_data.get("sparse_values", []),
                )
            } if version_data.get("sparse_indices") else {},
            payload={
                "patient_id": version_data["patient_id"],
                "doctor_id": version_data["doctor_id"],
                "version_id": point_id,
                "version_number": version_data.get("version_number", 1),
                "timestamp": version_data.get("timestamp"),
                "modality": version_data.get("modality", "text"),
                "version_hash": version_data.get("version_hash"),
                "author": version_data.get("author"),
                "edit_type": version_data.get("edit_type"),
                "summary": version_data.get("summary"),
                "tags": version_data.get("tags", []),
                "clinical_significance": version_data.get("clinical_significance", 0.0),
            },
        )

        await asyncio.to_thread(
            client.upsert,
            collection_name=PATIENT_VERSION_COLLECTION,
            points=[point],
            wait=True,
        )
        return point_id

    async def search_versions(
        self,
        patient_id: str,
        doctor_id: str,
        query_vector: List[float],
        vector_name: str = "medical_text",
        limit: int = 20,
        score_threshold: float = 0.3,
        use_hybrid: bool = True,
        sparse_vector: Optional[Dict[str, List]] = None,
        timestamp_lte: Optional[str] = None,
    ) -> List[ScoredPoint]:
        """Hybrid search with temporal filter and doctor isolation."""
        client = await self.connect()

        # Build filter: doctor isolation + patient + optional time
        filter_conditions = [
            FieldCondition(key="doctor_id", match=MatchValue(value=doctor_id)),
            FieldCondition(key="patient_id", match=MatchValue(value=patient_id)),
        ]
        if timestamp_lte:
            filter_conditions.append(
                FieldCondition(key="timestamp", range=Range(lte=timestamp_lte))
            )

        filter_obj = Filter(must=filter_conditions)
        search_params = SearchParams(hnsw_ef=128, exact=False)

        # Hybrid search: use SearchRequest for dense + sparse
        if use_hybrid and vector_name != "image" and sparse_vector:
            sparse = SparseVector(
                indices=sparse_vector.get("indices", []),
                values=sparse_vector.get("values", []),
            )
            search_requests = [
                SearchRequest(
                    vector=(vector_name, query_vector),
                    filter=filter_obj,
                    limit=limit * 2,  # over-fetch for fusion
                    params=search_params,
                    with_payload=True,
                ),
            ]
            if sparse.indices and sparse.values:
                search_requests.append(
                    SearchRequest(
                        vector=sparse,
                        filter=filter_obj,
                        limit=limit * 2,
                        params=search_params,
                        with_payload=True,
                    )
                )

            results = await asyncio.to_thread(
                client.search_batch,
                collection_name=PATIENT_VERSION_COLLECTION,
                requests=search_requests,
            )

            if len(results) > 1:
                fused = self._reciprocal_rank_fusion(
                    [list(r) for r in results],
                    k=limit,
                )
                return fused[:limit]

            return results[0][:limit] if results else []

        # Dense-only search
        results = await asyncio.to_thread(
            client.search,
            collection_name=PATIENT_VERSION_COLLECTION,
            query_vector=(vector_name, query_vector),
            query_filter=filter_obj,
            limit=limit,
            score_threshold=score_threshold,
            search_params=search_params,
            with_payload=True,
        )
        return results

    def _reciprocal_rank_fusion(
        self, result_lists: List[List[ScoredPoint]], k: int = 60, top_n: int = 20
    ) -> List[ScoredPoint]:
        """Reciprocal Rank Fusion (RRF) for combining multiple search results."""
        scores = {}
        for rank_list in result_lists:
            for rank, point in enumerate(rank_list):
                point_id = str(point.id)
                scores[point_id] = scores.get(point_id, 0.0) + 1.0 / (k + rank + 1)

        scored_points = {}
        for rank_list in result_lists:
            for point in rank_list:
                pid = str(point.id)
                if pid not in scored_points:
                    scored_points[pid] = point

        sorted_ids = sorted(scores.keys(), key=lambda pid: -scores[pid])
        fused = []
        for pid in sorted_ids[:top_n]:
            pt = scored_points[pid]
            # Copy to avoid mutating shared Qdrant response objects
            fused.append(ScoredPoint(
                id=pt.id,
                version=pt.version,
                score=scores[pid],
                payload=pt.payload,
                vector=pt.vector,
                shard_key=pt.shard_key,
                order_value=pt.order_value,
            ))
        return fused

    async def search_image_similar(
        self,
        patient_id: str,
        doctor_id: str,
        image_vector: List[float],
        limit: int = 10,
        score_threshold: float = 0.4,
        use_projector: bool = True,
    ) -> List[ScoredPoint]:
        """Image-only similarity search.

        If a trained projector (Feature C) is available and use_projector=True,
        projects the BiomedCLIP 512d vector to BGE-M3 1024d space and searches
        the 'hybrid' vector instead of 'image' vector for cross-modal retrieval.
        """
        client = await self.connect()

        # Try to use projector for cross-modal search (Feature C)
        W = _get_projector() if use_projector else None
        query_vec = image_vector
        vector_name = "image"

        if W is not None:
            import numpy as np
            # Project BiomedCLIP (512) -> BGE-M3 (1024)
            img_np = np.array(image_vector, dtype=np.float32).reshape(1, -1)
            projected = img_np @ W.T  # (1, 1024)
            query_vec = projected[0].tolist()
            vector_name = "hybrid"
            logger.debug("Feature C: Using projector for cross-modal image search")

        return await asyncio.to_thread(
            client.search,
            collection_name=PATIENT_VERSION_COLLECTION,
            query_vector=(vector_name, query_vec),
            query_filter=Filter(must=[
                FieldCondition(key="doctor_id", match=MatchValue(value=doctor_id)),
                FieldCondition(key="patient_id", match=MatchValue(value=patient_id)),
            ]),
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )

    async def delete_version(self, version_id: str) -> bool:
        """Delete a version point."""
        client = await self.connect()
        result = await asyncio.to_thread(
            client.delete,
            collection_name=PATIENT_VERSION_COLLECTION,
            points_selector=[uuid.UUID(version_id)],
            wait=True,
        )
        return result.status == UpdateStatus.COMPLETED

    async def get_version(self, version_id: str) -> Optional[ScoredPoint]:
        """Get a single version by ID."""
        client = await self.connect()
        results = await asyncio.to_thread(
            client.retrieve,
            collection_name=PATIENT_VERSION_COLLECTION,
            ids=[uuid.UUID(version_id)],
            with_payload=True,
            with_vectors=True,
        )
        return results[0] if results else None

    async def get_patient_versions(self, patient_id: str, doctor_id: str, limit: int = 100) -> List[ScoredPoint]:
        """Get all versions for a patient (for timeline)."""
        client = await self.connect()
        results = await asyncio.to_thread(
            client.scroll,
            collection_name=PATIENT_VERSION_COLLECTION,
            scroll_filter=Filter(must=[
                FieldCondition(key="patient_id", match=MatchValue(value=patient_id)),
                FieldCondition(key="doctor_id", match=MatchValue(value=doctor_id)),
            ]),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return results[0]

    async def get_patient_vectors(
        self,
        patient_id: str,
        doctor_id: str,
        vector_name: str = "medical_text",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch a patient's version vectors for trajectory analysis (Feature E).

        Returns a list of {"version_number", "timestamp", "vector"} sorted by
        version_number ascending (oldest first). Versions lacking the named
        vector are skipped.
        """
        client = await self.connect()
        points, _ = await asyncio.to_thread(
            client.scroll,
            collection_name=PATIENT_VERSION_COLLECTION,
            scroll_filter=Filter(must=[
                FieldCondition(key="patient_id", match=MatchValue(value=patient_id)),
                FieldCondition(key="doctor_id", match=MatchValue(value=doctor_id)),
            ]),
            limit=limit,
            with_payload=True,
            with_vectors=[vector_name],
        )
        out = []
        for p in points:
            vec = (p.vector or {}).get(vector_name) if isinstance(p.vector, dict) else None
            if not vec:
                continue
            out.append({
                "version_number": (p.payload or {}).get("version_number", 0),
                "timestamp": (p.payload or {}).get("timestamp"),
                "vector": vec,
            })
        out.sort(key=lambda r: r["version_number"])
        return out

    async def count_versions(self, patient_id: str, doctor_id: str) -> int:
        client = await self.connect()
        count = await asyncio.to_thread(
            client.count,
            collection_name=PATIENT_VERSION_COLLECTION,
            count_filter=Filter(must=[
                FieldCondition(key="patient_id", match=MatchValue(value=patient_id)),
                FieldCondition(key="doctor_id", match=MatchValue(value=doctor_id)),
            ]),
            exact=True,
        )
        return count.count


# Global instance
qdrant_service = QdrantService()