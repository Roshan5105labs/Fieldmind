import json
import os

from qdrant_client import QdrantClient, models

from common.config import CORPUS_DIR, DENSE, DIM, FLEET_COLLECTION, QDRANT_URL, SPARSE
from common.embeddings import Embedder, index_text, point_id
from cloud.state import CloudState

def to_server_sparse(sv):
    return models.SparseVector(indices=list(sv.indices), values=list(sv.values))


def create_collection(client):
    client.create_collection(
        collection_name=FLEET_COLLECTION,
        vectors_config={DENSE: models.VectorParams(size=DIM, distance=models.Distance.COSINE)},
        sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )


def seed(reset=True):
    client = QdrantClient(url=QDRANT_URL)
    exists = client.collection_exists(FLEET_COLLECTION)
    if reset and exists:
        client.delete_collection(FLEET_COLLECTION)
        exists = False
    if not exists:
        create_collection(client)
    elif not reset:
        print(f"Preserving existing '{FLEET_COLLECTION}' collection")
        return

    records = json.loads((CORPUS_DIR / "fleet.json").read_text(encoding="utf-8"))
    embedder = Embedder()
    texts = [index_text(r) for r in records]
    dense_vecs = embedder.dense_docs(texts)

    points = [
        models.PointStruct(
            id=point_id(r["doc_id"]),
            vector={DENSE: d, SPARSE: to_server_sparse(embedder.sparse_doc(t))},
            payload=r,
        )
        for r, t, d in zip(records, texts, dense_vecs)
    ]
    client.upsert(collection_name=FLEET_COLLECTION, points=points, wait=True)
    CloudState().reset(records)
    print(f"Seeded {client.count(FLEET_COLLECTION).count} records into '{FLEET_COLLECTION}'")


if __name__ == "__main__":
    reset_on_start = os.getenv("FIELDMIND_RESET_ON_START", "false").lower() in {
        "1", "true", "yes", "on",
    }
    seed(reset=reset_on_start)
