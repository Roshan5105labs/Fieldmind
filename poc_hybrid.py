import shutil
import time
from pathlib import Path

from fastembed import TextEmbedding
from qdrant_edge import (
    Distance, EdgeConfig, EdgeShard, EdgeVectorParams,
    EdgeSparseVectorParams, Modifier, Bm25, Bm25Config,
    Point, UpdateOperation, Query, QueryRequest,
)

MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODELS_DIR = "./models"
SHARD_DIR = "./storage/poc_hybrid"
DENSE = "dense"
SPARSE = "bm25"
DIM = 384

dense_model = TextEmbedding(model_name=MODEL_NAME, cache_dir=MODELS_DIR, local_files_only=True)
bm25 = Bm25(Bm25Config(language="english"))

shutil.rmtree(SHARD_DIR, ignore_errors=True)
Path(SHARD_DIR).mkdir(parents=True, exist_ok=True)

config = EdgeConfig(
    vectors={DENSE: EdgeVectorParams(size=DIM, distance=Distance.Cosine)},
    sparse_vectors={SPARSE: EdgeSparseVectorParams(modifier=Modifier.Idf)},
)
shard = EdgeShard.create(SHARD_DIR, config)

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

texts = [index_text(r) for r in records]
dense_vecs = [v.tolist() for v in dense_model.embed(texts)]

points = [
    Point(
        id=i + 1,
        vector={DENSE: dv, SPARSE: bm25.embed_document(t)},
        payload=r,
    )
    for i, (r, t, dv) in enumerate(zip(records, texts, dense_vecs))
]
shard.update(UpdateOperation.upsert_points(points))
shard.optimize()
print(f"Inserted {len(points)} records with dense + BM25 vectors")

def rrf(result_lists, k=60):
    scores, payloads = {}, {}
    for results in result_lists:
        for rank, hit in enumerate(results, start=1):
            key = str(hit.id)
            scores[key] = scores.get(key, 0) + 1 / (k + rank)
            payloads[key] = hit.payload
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [payloads[key] for key, _ in ranked]

def run_query(vector, using, limit=5):
    return shard.query(QueryRequest(
        query=Query.Nearest(vector, using=using),
        limit=limit,
        with_vector=False,
        with_payload=True,
    ))


def label(p):
    return f"{p['fault_code']}/{p['equipment']}"


def compare(question):
    start = time.perf_counter()
    dense_hits = run_query(list(dense_model.embed([question]))[0].tolist(), DENSE)
    sparse_hits = run_query(bm25.embed_query(question), SPARSE)
    fused = rrf([dense_hits, sparse_hits])
    ms = (time.perf_counter() - start) * 1000

    print(f"\nQ: {question}   ({ms:.1f} ms total)")
    print("  dense :", [label(h.payload) for h in dense_hits[:3]])
    print("  bm25  :", [label(h.payload) for h in sparse_hits[:3]])
    print("  hybrid:", [label(p) for p in fused[:3]])


compare("E417")
compare("motor gets very hot after running for a while")
compare("machine shaking at high speed")
compare("E417 overheating on CNC-14")
compare("loose connector causing overheating")

shard.close()