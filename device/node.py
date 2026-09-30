import shutil
import tempfile
import time
from pathlib import Path

import requests
from qdrant_edge import (
    Distance, EdgeConfig, EdgeShard, EdgeSparseVectorParams, EdgeVectorParams,
    Modifier, Point, Query, QueryRequest, UpdateOperation,
)

from common.config import (
    DENSE, DEVICES, DIM, FLEET_COLLECTION, QDRANT_URL, SPARSE, STORAGE_DIR, SYNC_API_URL,
)
from common.embeddings import Embedder, index_text, point_id
from device.outbox import Outbox
from device.policy import decide

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
        self.outbox = Outbox(self.root / "device.db")

        self.local = self._open_local()
        self.fleet = EdgeShard.load(str(self.fleet_dir)) if self._has_data(self.fleet_dir) else None

    # ---------- opening shards ----------

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

    # ---------- pulling fleet knowledge (cloud -> device) ----------

    def pull_fleet(self):
        self._require_online()
        result = self._pull_full() if self.fleet is None else self._pull_partial()
        self.outbox.log("pull", f"{result['mode']} snapshot, {result['bytes'] / 1024:.0f} KB")
        return result

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

    def fleet_version(self, doc_id):
        if self.fleet is None:
            return None
        records = self.fleet.retrieve([point_id(doc_id)], with_payload=True, with_vector=False)
        return records[0].payload.get("version") if records else None

    # ---------- logging notes on the device ----------

    def log_note(self, note):
        record = {**note, "logged_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        text = index_text(record)
        point = Point(
            id=point_id(record["note_id"]),
            vector={DENSE: self.embedder.dense_query(text), SPARSE: self.embedder.sparse_doc(text)},
            payload=record,
        )
        self.local.update(UpdateOperation.upsert_points([point]))

        base_version = self.fleet_version(record["edits_doc_id"]) if record.get("edits_doc_id") else None
        decision = decide(record)
        self.outbox.add(record, decision, base_version)
        return record, decision

        # ---------- pushing notes (device -> cloud) ----------

    def sync_now(self, budget_bytes=None):
        self._require_online()
        summary = {"sent": [], "conflicts": [], "deferred": [], "bytes": 0}

        for item in self.outbox.items(status="pending"):
            size = item["size_bytes"]
            if budget_bytes is not None and summary["bytes"] + size > budget_bytes:
                summary["deferred"].append(item["note_id"])
                self.outbox.log("deferred", f"{item['note_id']} ({size} B) exceeds remaining budget")
                continue

            try:
                resp = requests.post(
                    f"{SYNC_API_URL}/push",
                    json={"device": self.device_id, "note": item["payload"],
                          "base_version": item["base_version"]},
                    timeout=30,
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                self.outbox.log("push_failed", f"{item['note_id']}: {e}; will retry next sync")
                break

            result = resp.json()
            summary["bytes"] += size
            if result["status"] in ("accepted", "applied_edit", "duplicate"):
                self.outbox.set_status(item["note_id"], "synced")
                summary["sent"].append(item["note_id"])
            else:
                self.outbox.set_status(item["note_id"], result["status"])
                summary["conflicts"].append(item["note_id"])
            self.outbox.log("push", f"{item['note_id']} -> {result['status']}")

        return summary
    def approve(self, note_id):
        self.outbox.set_status(note_id, "pending")
        self.outbox.log("approved", f"{note_id} approved by supervisor; queued for sync")

    # ---------- hybrid search across both shards ----------

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
                key = str(h.id)
                entry = results.setdefault(key, {
                    "source": source, "payload": h.payload, "rrf": 0.0, "dense_score": None,
                })
                if entry["source"] != source:
                    entry["source"] = "fleet+local"
                entry["rrf"] += 1 / (k + rank)
                if method == "dense":
                    entry["dense_score"] = h.score

        return sorted(results.values(), key=lambda e: e["rrf"], reverse=True)[:limit]

    # ---------- shutdown ----------

    def close(self):
        self.local.close()
        if self.fleet is not None:
            self.fleet.close()
        self.outbox.close()


if __name__ == "__main__":
    import json
    from common.config import CORPUS_DIR

    embedder = Embedder()
    node = DeviceNode("device_a", embedder, reset=True)
    print("Pull:", node.pull_fleet())

    node.online = False
    print("\n--- device A goes offline and logs its notes ---")
    notes = json.loads((CORPUS_DIR / "field_notes.json").read_text(encoding="utf-8"))
    for note in (n for n in notes if n["device"] == "device_a"):
        node.log_note(note)

    print("\nOutbox:")
    for item in node.outbox.items():
        print(f"  {item['note_id']:6} {item['status']:13} p={item['priority']} "
              f"base_v={item['base_version']}  {item['reason']}")

    print("\nActivity (newest first):")
    for a in node.outbox.activity(limit=10):
        print(f"  {a['ts']}  {a['event']:9} {a['detail']}")

    node.close()