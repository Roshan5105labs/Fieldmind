import uuid

from fastembed import TextEmbedding
from qdrant_edge import Bm25, Bm25Config

from common.config import MODEL_NAME, MODELS_DIR


class Embedder:
    def __init__(self):
        self.dense_model = TextEmbedding(
            model_name=MODEL_NAME, cache_dir=str(MODELS_DIR), local_files_only=True
        )
        self.bm25 = Bm25(Bm25Config(language="english"))

    def dense_docs(self, texts):
        return [v.tolist() for v in self.dense_model.embed(texts)]

    def dense_query(self, text):
        return self.dense_docs([text])[0]

    def sparse_doc(self, text):
        return self.bm25.embed_document(text)

    def sparse_query(self, text):
        return self.bm25.embed_query(text)

def index_text(record):
    parts = [
        record.get("doc_id"),
        record.get("note_id"),
        record.get("fault_code"),
        record.get("asset_id"),
        record.get("equipment_type"),
        record.get("title"),
        record["text"],
    ]
    return " ".join(p for p in parts if p)


def point_id(key):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"fieldmind/{key}"))
