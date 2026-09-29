import shutil
import tempfile
import time
from pathlib import Path

import requests
from qdrant_edge import (
    Distance, EdgeConfig, EdgeShard, EdgeSparseVectorParams, EdgeVectorParams,
    Modifier, Point, Query, QueryRequest, UpdateOperation,
)

from common.config import DENSE, DEVICES, DIM, FLEET_COLLECTION, QDRANT_URL, SPARSE, STORAGE_DIR
from common.embeddings import Embedder, index_text, point_id

SNAPSHOT_URL = f"{QDRANT_URL}/collections/{FLEET_COLLECTION}/shards/0/snapshot"
PARTIAL_URL = f"{SNAPSHOT_URL}/partial/create"


class OfflineError(Exception):
    pass


def _download(url, dest, method="GET", json_body=None):
    resp = requests.request(method, url, json=json_body, stream=True, timeout=30)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def _local_config():
    return EdgeConfig(
        vectors={DENSE: EdgeVectorParams(size=DIM, distance=Distance.Cosine)},
        sparse_vectors={SPARSE: EdgeSparseVectorParams(modifier=Modifier.Idf)},
    )

class DeviceNode:
    def __init__(self, device_id, embedder, reset=False):
        self.device_id = device_id
        self.site_id = DEVICES[device_id]["site_id"]
        self.label = DEVICES[device_id]["label"]
        self.embedder = embedder
        self.online = True

        self.root = STORAGE_DIR / device_id
        self.fleet_dir = self.root / "fleet"
        self.local_dir = self.root / "local"
        if reset and self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

        self.local = self._open_local()
        self.fleet = EdgeShard.load(str(self.fleet_dir)) if self._has_data(self.fleet_dir) else None

    @staticmethod
    def _has_data(path):
        return path.exists() and any(path.iterdir())

    def _open_local(self):
        if self._has_data(self.local_dir):
            return EdgeShard.load(str(self.local_dir))
        self.local_dir.mkdir(parents=True, exist_ok=True)
        return EdgeShard.create(str(self.local_dir), _local_config())

    def _require_online(self):
        if not self.online:
            raise OfflineError(f"{self.label} is offline")

    def pull_fleet(self):
        self._require_online()
        if self.fleet is None:
            return self._pull_full()
        return self._pull_partial()

    def _pull_full(self):
        self.fleet_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
            snap = Path(tmp) / "shard.snapshot"
            _download(SNAPSHOT_URL, snap)
            size = snap.stat().st_size
            EdgeShard.unpack_snapshot(str(snap), str(self.fleet_dir))
        self.fleet = EdgeShard.load(str(self.fleet_dir))
        return {"mode": "full", "bytes": size}

    def _pull_partial(self):
        manifest = self.fleet.snapshot_manifest()
        with tempfile.TemporaryDirectory(dir=self.fleet_dir) as tmp:
            part = Path(tmp) / "partial.snapshot"
            _download(PARTIAL_URL, part, method="POST", json_body=manifest)
            size = part.stat().st_size
            self.fleet.update_from_snapshot(str(part))
        return {"mode": "partial", "bytes": size}
    
    def log_note(self, note):
        record = {**note, "logged_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        text = index_text(record)
        point = Point(
            id=point_id(record["note_id"]),
            vector={DENSE: self.embedder.dense_query(text), SPARSE: self.embedder.sparse_doc(text)},
            payload=record,
        )
        self.local.update(UpdateOperation.upsert_points([point]))
        return record

    def _query(self, shard, vector, using, limit=10):
            return shard.query(QueryRequest(
            query=Query.Nearest(vector, using=using),
            limit=limit, with_vector=False, with_payload=True,
        ))

    def search(self, question, limit=5, k=60):
        dense_q = self.embedder.dense_query(question)
        sparse_q = self.embedder.sparse_query(question)

        dense_hits = []
        ranked_lists = []
        for source, shard in (("fleet", self.fleet), ("local", self.local)):
            if shard is None:
                continue
            dense_hits += [(source, h) for h in self._query(shard, dense_q, DENSE)]
            ranked_lists.append(("bm25", [(source, h) for h in self._query(shard, sparse_q, SPARSE)]))

        dense_hits.sort(key=lambda x: x[1].score, reverse=True)
        ranked_lists.append(("dense", dense_hits))

        results = {}
        for method, hits in ranked_lists:
            for rank, (source, h) in enumerate(hits, start=1):
                entry = results.setdefault(f"{source}:{h.id}", {
                    "source": source, "payload": h.payload, "rrf": 0.0, "dense_score": None,
                })
                entry["rrf"] += 1 / (k + rank)
                if method == "dense":
                    entry["dense_score"] = h.score

        return sorted(results.values(), key=lambda e: e["rrf"], reverse=True)[:limit]

    def close(self):
        self.local.close()
        if self.fleet is not None:
            self.fleet.close()

if __name__ == "__main__":
    import json
    from common.config import CORPUS_DIR

    embedder = Embedder()
    node = DeviceNode("device_a", embedder, reset=True)
    print("Pull:", node.pull_fleet())

    def show(question):
        start = time.perf_counter()
        results = node.search(question, limit=3)
        ms = (time.perf_counter() - start) * 1000
        print(f"\nQ: {question}   ({ms:.1f} ms)")
        for r in results:
            p = r["payload"]
            ident = p.get("doc_id") or p.get("note_id")
            print(f"  [{r['source']:5}] {ident}: {p['text'][:60]}...")

    show("E417 spindle overheating")
    show("conveyor belt slipping under load")

    node.online = False
    print("\n--- device A goes offline ---")
    notes = json.loads((CORPUS_DIR / "field_notes.json").read_text(encoding="utf-8"))
    node.log_note(next(n for n in notes if n["note_id"] == "FN-A1"))
    print("Logged FN-A1 while offline")
    show("E417 alarm in the afternoon, cabinet too hot")
    q = "E417 alarm in the afternoon, cabinet too hot"
    dq, sq = embedder.dense_query(q), embedder.sparse_query(q)
    for source, shard in (("fleet", node.fleet), ("local", node.local)):
        d = node._query(shard, dq, DENSE, limit=3)
        s = node._query(shard, sq, SPARSE, limit=3)
        name = lambda h: h.payload.get("doc_id") or h.payload.get("note_id")
        print(f"  {source} dense: {[(name(h), round(h.score, 3)) for h in d]}")
        print(f"  {source} bm25 : {[(name(h), round(h.score, 3)) for h in s]}")

    try:
        node.pull_fleet()
    except OfflineError as e:
        print("\nPull blocked:", e)

    node.close()