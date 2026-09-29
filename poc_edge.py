import shutil
import time
from pathlib import Path

from fastembed import TextEmbedding
from qdrant_edge import (
    Distance, EdgeConfig, EdgeShard, EdgeVectorParams,
    Point, UpdateOperation, Query, QueryRequest,
)

MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODELS_DIR = "./models"
SHARD_DIR = "./data/poc_shard"
VECTOR_NAME = "dense"
DIM = 384

model = TextEmbedding(model_name=MODEL_NAME, cache_dir=MODELS_DIR, local_files_only=True)


def embed_many(texts):
    return [v.tolist() for v in model.embed(texts)]

shutil.rmtree(SHARD_DIR, ignore_errors=True)
Path(SHARD_DIR).mkdir(parents=True, exist_ok=True)

config = EdgeConfig(
    vectors={VECTOR_NAME: EdgeVectorParams(size=DIM, distance=Distance.Cosine)}
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
]

vectors = embed_many([r["text"] for r in records])
points = [
    Point(id=i + 1, vector={VECTOR_NAME: vec}, payload=rec)
    for i, (rec, vec) in enumerate(zip(records, vectors))
]
shard.update(UpdateOperation.upsert_points(points))
print(f"Inserted {len(points)} records")

def search(question, limit=3):
    start = time.perf_counter()
    q_vec = embed_many([question])[0]
    hits = shard.query(QueryRequest(
        query=Query.Nearest(q_vec, using=VECTOR_NAME),
        limit=limit,
        with_vector=False,
        with_payload=True,
    ))
    ms = (time.perf_counter() - start) * 1000
    print(f"\nQ: {question}   ({ms:.1f} ms)")
    for h in hits:
        print(f"  score={h.score:.3f}  [{h.payload['fault_code']}] {h.payload['equipment']}: {h.payload['text'][:60]}...")


search("motor gets very hot after running for a while")
search("machine shaking at high speed")
search("E417")

new_fix = {"fault_code": "E417", "equipment": "CNC-14",
           "text": "Motor overheating after 20 minutes. Thermal sensor connector was loose, giving false readings. Reseated connector and verified stable for 45 minutes."}
new_vec = embed_many([new_fix["text"]])[0]
shard.update(UpdateOperation.upsert_points([
    Point(id=7, vector={VECTOR_NAME: new_vec}, payload=new_fix)
]))
print("\nLearned a new fix on the device.")
search("loose connector causing overheating")

shard.close()
shard = EdgeShard.load(SHARD_DIR)
print("\nShard closed and reloaded from disk.")
search("loose connector causing overheating")
shard.close()