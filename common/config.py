from pathlib import Path

MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODELS_DIR = Path("./models")
STORAGE_DIR = Path("./storage")
CORPUS_DIR = Path("./data/corpus")

DENSE = "dense"
SPARSE = "bm25"
DIM = 384

QDRANT_URL = "http://localhost:6333"
FLEET_COLLECTION = "fleet_knowledge"

DEVICES = {
    "device_a": {"site_id": "CHN-01", "label": "EDGE-CHN-01"},
    "device_b": {"site_id": "PUN-02", "label": "EDGE-PUN-02"},
}