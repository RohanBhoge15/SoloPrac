"""Qdrant Vector Store Service — named vectors, hybrid search, payload filtering."""

import os
import json
import uuid
import logging
from typing import List, Dict, Any, Optional, Literal
from contextlib import asynccontextmanager

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition,
    Range, MatchValue, SearchRequest, SearchParams, UpdateStatus,
    PayloadSchemaType, SparseVectorParams, SparseVector,
    NamedVector, NamedVectorList, ScoredPoint,
)

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Collection Config ───
PATIENT_VERSION_COLLECTION = "patient_versions"

VECTOR_CONFIG = {
    "medical_text": {"size": 768, "distance": Distance.COSINE},    # MedCPT
    "hybrid": {"size": 1024, "distance": Distance.COSINE},         # BGE-M3 dense
    "image": {"size": 512, "distance": Distance.COSINE},           # NV-CLIP
}

SPARSE_VECTOR_NAME = "sparse"


class QdrantService:
    """Qdrant vector store for patient versions with hybrid multimodal search."""

    def __init__(self):
        self._client: Optional[QdrantClient] = None

    async def connect(self) -> QdrantClient:
        if self._client is not None:
            return self._client

        self._client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            timeout=10,
        )
        # Test connection
        self._client.get_collections()
        await self._ensure_collection()
        return self._client

    async def _ensure_collection(self):
        """Create collection with named vectors if it doesn't exist."""
        client = await self.connect()
        collections = client.get_collections().collections
        names = [c.name for c in collections]

        if PATIENT_VERSION_COLLECTION not in names:
            logger.info(f"Creating collection: {PATIENT_VERSION_COLLECTION}")
            client.create_collection(
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
            client.create_payload_index(
                collection_name=PATIENT_VERSION_COLLECTION,
                field_name="patient_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            client.create_payload_index(
                collection_name=PATIENT_VERSION_COLLECTION,
                field_name="doctor_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            client.create_payload_index(
                collection_name=PATIENT_VERSION_COLLECTION,
                field_name="timestamp",
                field_schema=PayloadSchemaType.DATETIME,
            )
            client.create_payload_index(
                collection_name=PATIENT_VERSION_COLLECTION,
                field_name="modality",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            client.create_payload_index(
                collection_name=PATIENT_VERSION_COLLECTION,
                field_name="version_number",
                field_schema=PayloadSchemaType.INTEGER,
            )
            client.create_payload_index(
                collection_name=PATIENT_VERSION_COLLECTION,
                field_name="clinical_significance",
                field_schema=PayloadSchemaType.FLOAT,
            )

    # ─── Point Operations ───

    async def upsert_version(self, version_data: Dict[str, Any]) -> str:
        """Upsert a patient version point with all vector representations."""
        client = await self.connect()

        # Generate point ID (use version_id if available, else generate)
        point_id = str(uuid.uuid4())
        version_id = version_data.get("version_id")
        if version_id:
            point_id = str(version_id)

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

        client = await self.connect()
        client.upsert(
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

        # Search
        if use_hybrid and vector_name != "image":
            # Hybrid: dense + sparse
            sparse_vector = SparseVector(
                indices=[],  # would come from BGE-M3 sparse
                values=[],
            )
            # For now, just dense + filter
            results = client.search(
                collection_name=PATIENT_VERSION_COLLECTION,
                query_vector=(vector_name, query_vector),
                query_filter=filter_obj,
                limit=limit,
                score_threshold=score_threshold,
                search_params=SearchParams(hnsw_ef=128, exact=False),
                with_payload=True,
            )
        else:
            # Dense search
            results = client.search(
                collection_name=PATIENT_VERSION_COLLECTION,
                query_vector=(vector_name, query_vector),
                query_filter=filter_obj,
                limit=limit,
                score_threshold=score_threshold,
                search_params=SearchParams(hnsw_ef=128, exact=False),
                with_payload=True,
            )

        return results

    async def search_image_similar(
        self,
        patient_id: str,
        doctor_id: str,
        image_vector: List[float],
        limit: int = 10,
        score_threshold: float = 0.4,
    ) -> List[ScoredPoint]:
        """Image-only similarity search (ORB + NV-CLIP fallback)."""
        client = await self.connect()
        return client.search(
            collection_name=PATIENT_VERSION_COLLECTION,
            query_vector=("image", image_vector),
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
        result = client.delete(
            collection_name=PATIENT_VERSION_COLLECTION,
            points_selector=[uuid.UUID(version_id)],
            wait=True,
        )
        return result.status == UpdateStatus.COMPLETED

    async def get_version(self, version_id: str) -> Optional[ScoredPoint]:
        """Get a single version by ID."""
        client = await self.connect()
        results = client.retrieve(
            collection_name=PATIENT_VERSION_COLLECTION,
            ids=[uuid.UUID(version_id)],
            with_payload=True,
            with_vectors=True,
        )
        return results[0] if results else None

    async def get_patient_versions(self, patient_id: str, doctor_id: str, limit: int = 100) -> List[ScoredPoint]:
        """Get all versions for a patient (for timeline)."""
        client = await self.connect()
        results = client.scroll(
            collection_name=PATIENT_VERSION_COLLECTION,
            scroll_filter=Filter(must=[
                FieldCondition(key="patient_id", match=MatchValue(value=patient_id)),
                FieldCondition(key="doctor_id", match=MatchValue(value=doctor_id)),
            ]),
            limit=limit,
            with_payload=True,
            with_vectors=False,
            order_by="timestamp",
        )
        return results[0]

    async def count_versions(self, patient_id: str, doctor_id: str) -> int:
        client = await self.connect()
        count = client.count(
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