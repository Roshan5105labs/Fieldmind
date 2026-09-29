import shutil
import tempfile
from pathlib import Path

import requests
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models
from qdrant_edge import EdgeShard, Bm25, Bm25Config, Query, QueryRequest

QDRANT_URL = "http://localhost:6333"
COLLECTION = "fleet_knowledge"
FLEET_DIR = Path("./storage/poc_device/fleet")
MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODELS_DIR = "./models"
DENSE = "dense"
SPARSE = "bm25"
DIM = 384

dense_model = TextEmbedding(model_name=MODEL_NAME, cache_dir=MODELS_DIR, local_files_only=True)
bm25 = Bm25(Bm25Config(language="english"))

records = [
    {"fault_code": "E417", "equipment": "CNC-11",
     "text": "Spindle motor overheated after 25 minutes. Cooling fan intake blocked by metal shavings. Cleaned fan and recalibrated thermal sensor."},
    {"fault_code": "E102", "equipment": "PLC-X300",
     "text": "PLC lost communication with HMI panel. Ethernet cable damaged near cabinet door hinge. Replaced cable."},
    {"fault_code": "H220", "equipment": "PRESS-04",
     "text": "Hydraulic pressure dropping during stroke. Worn seal on main cylinder causing leak. Replaced seal kit."},
    {"fault_code": "V310", "equipment": "CNC-09",
     "text": "Excessive spindle vibration at high RPM. Tool holder not seated correctly. Cleaned taper and reseated holder."},
    {"fault_code": "C050", "equipment": "CONV-02",
     "text": "Conveyor belt slipping under load. Belt tension too low after maintenance. Adjusted tensioner to spec."},
    {"fault_code": "P611", "equipment": "PUMP-07",
     "text": "Coolant pump making grinding noise and low flow. Impeller damaged by debris. Replaced impeller and added inlet strainer."},
     {"fault_code": "E417", "equipment": "CNC-14",
     "text": "Motor overheating after 20 minutes. Thermal sensor connector was loose, giving false readings. Reseated connector and verified stable for 45 minutes."},
]
def index_text(r):
    return f"{r['fault_code']} {r['equipment']} {r['text']}"

client = QdrantClient(url=QDRANT_URL)

if client.collection_exists(COLLECTION):
    client.delete_collection(COLLECTION)

client.create_collection(
    collection_name=COLLECTION,
    vectors_config={DENSE: models.VectorParams(size=DIM, distance=models.Distance.COSINE)},
    sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
)


def to_server_sparse(sv):
    return models.SparseVector(indices=list(sv.indices), values=list(sv.values))


def upload(recs, start_id):
    texts = [index_text(r) for r in recs]
    dense = [v.tolist() for v in dense_model.embed(texts)]
    points = [
        models.PointStruct(
            id=start_id + i,
            vector={DENSE: d, SPARSE: to_server_sparse(bm25.embed_document(t))},
            payload=r,
        )
        for i, (r, t, d) in enumerate(zip(recs, texts, dense))
    ]
    client.upsert(collection_name=COLLECTION, points=points, wait=True)


upload(records, start_id=1)
print("Points on server:", client.count(COLLECTION).count)
def download(url, dest, method="GET", json_body=None):
    resp = requests.request(method, url, json=json_body, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


if FLEET_DIR.exists():
    shutil.rmtree(FLEET_DIR)
FLEET_DIR.mkdir(parents=True)

with tempfile.TemporaryDirectory(dir=FLEET_DIR.parent) as tmp:
    snap = Path(tmp) / "shard.snapshot"
    download(f"{QDRANT_URL}/collections/{COLLECTION}/shards/0/snapshot", snap)
    print(f"Full snapshot size: {snap.stat().st_size / 1024:.0f} KB")
    EdgeShard.unpack_snapshot(str(snap), str(FLEET_DIR))

fleet = EdgeShard.load(str(FLEET_DIR))
print("Fleet shard loaded on device")


def hybrid_search(shard, question, limit=3):
    def run(vector, using):
        return shard.query(QueryRequest(
            query=Query.Nearest(vector, using=using),
            limit=5, with_vector=False, with_payload=True,
        ))

    dense_hits = run(list(dense_model.embed([question]))[0].tolist(), DENSE)
    sparse_hits = run(bm25.embed_query(question), SPARSE)

    scores, payloads = {}, {}
    for hits in (dense_hits, sparse_hits):
        for rank, h in enumerate(hits, start=1):
            key = str(h.id)
            scores[key] = scores.get(key, 0) + 1 / (60 + rank)
            payloads[key] = h.payload
    ranked = sorted(scores, key=scores.get, reverse=True)[:limit]

    print(f"\nQ: {question}")
    for key in ranked:
        p = payloads[key]
        print(f"  {p['fault_code']}/{p['equipment']}: {p['text'][:55]}...")


hybrid_search(fleet, "E417")
hybrid_search(fleet, "loose connector causing overheating")

new_fix = {"fault_code": "C050", "equipment": "CONV-05",
           "text": "Belt slipping on incline section. Drive roller lagging worn smooth. Replaced roller lagging and re-tensioned belt."}
upload([new_fix], start_id=8)
print("\nNew fix added on server. Points on server:", client.count(COLLECTION).count)

manifest = fleet.snapshot_manifest()
with tempfile.TemporaryDirectory(dir=FLEET_DIR) as tmp:
    part = Path(tmp) / "partial.snapshot"
    download(
        f"{QDRANT_URL}/collections/{COLLECTION}/shards/0/snapshot/partial/create",
        part, method="POST", json_body=manifest,
    )
    print(f"Partial snapshot size: {part.stat().st_size / 1024:.0f} KB")
    fleet.update_from_snapshot(str(part))

hybrid_search(fleet, "worn drive roller on conveyor")
fleet.close()