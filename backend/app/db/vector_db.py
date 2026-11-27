import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
from app.config import config


class VectorDBManager:
    """ChromaDB interface for face embeddings (cosine space).

    Each enrolled photo produces its own vector so a single person may own
    several embeddings (aging, angles, re-enrolment). `embedding_id` is unique
    per photo (e.g. `EMP01::photo.jpg`) while `person_id` groups them.
    """

    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=str(config.VECTOR_DB_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name="face_embeddings",
            metadata={"hnsw:space": "cosine"},
        )

    def _stored_dim(self) -> Optional[int]:
        """Dimension of the vectors already persisted, if any."""
        try:
            got = self.collection.get(include=["embeddings"], limit=1)
            embs = got.get("embeddings")
            if embs is not None and len(embs) > 0 and embs[0] is not None:
                return len(embs[0])
        except Exception:
            pass
        return None

    def _ensure_dim(self, dim: int):
        """Rebuild the collection if the embedding dimensionality changed
        (e.g. index written by the legacy dlib backend is 128-d but the
        insightface backend emits 512-d). Chroma refuses mixed dims in one
        collection, so wipe and start fresh on a guaranteed mismatch."""
        stored = self._stored_dim()
        if stored is not None and stored != dim:
            print(f"[VectorDB] embedding dim changed {stored}->{dim}; rebuilding face_embeddings collection")
            self.reset_face_embeddings()

    def reset_face_embeddings(self):
        """Drop and recreate the collection (also used on backend dimension change)."""
        try:
            self.client.delete_collection("face_embeddings")
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name="face_embeddings",
            metadata={"hnsw:space": "cosine"},
        )

    def add_face_embedding(
        self,
        embedding_id: str,
        person_id: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ):
        """Upsert a single face snapshot. embedding_id must be unique."""
        self._ensure_dim(len(embedding))
        meta = {**(metadata or {}), "person_id": person_id, "embedding_id": embedding_id}
        try:
            self.collection.upsert(
                ids=[embedding_id],
                embeddings=[embedding],
                metadatas=[meta],
            )
        except Exception as e:
            if "dimension" not in str(e).lower():
                raise
            # Chroma pins a dimension per collection even when empty (e.g. an
            # index from the previous backend). Recreate the collection and retry.
            print(f"[VectorDB] dimension mismatch on write; rebuilding collection: {e}")
            self.reset_face_embeddings()
            self.collection.upsert(
                ids=[embedding_id],
                embeddings=[embedding],
                metadatas=[meta],
            )

    def query_face(self, embedding: List[float], n_results: int = 1) -> Dict[str, Any]:
        """Return closest vector as (person_id, cosine distance, metadata)."""
        self._ensure_dim(len(embedding))
        if self.collection.count() == 0:
            return {"match_id": None, "embedding_id": None, "distance": 1.0, "metadata": {}}

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
        )

        if not results or not results["ids"] or not results["ids"][0]:
            return {"match_id": None, "embedding_id": None, "distance": 1.0, "metadata": {}}

        embedding_id = results["ids"][0][0]
        distance = results["distances"][0][0]
        metadata = results["metadatas"][0][0] if results.get("metadatas") else {}
        person_id = metadata.get("person_id", embedding_id)

        return {
            "match_id": person_id,
            "embedding_id": embedding_id,
            "distance": float(distance),
            "metadata": metadata,
        }

    def delete_person_embeddings(self, person_id: str):
        """Remove every vector belonging to a person."""
        try:
            self.collection.delete(where={"person_id": person_id})
        except Exception:
            pass

    def count_embeddings(self) -> int:
        try:
            return self.collection.count()
        except Exception:
            return 0

    def count_persons(self) -> int:
        """Distinct person_id count across stored metadata."""
        try:
            data = self.collection.get(include=["metadatas"])
            ids = {m.get("person_id") for m in (data.get("metadatas") or []) if m}
            return len(ids)
        except Exception:
            return 0


vector_db = VectorDBManager()