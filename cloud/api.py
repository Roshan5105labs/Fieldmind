from fastapi import FastAPI
from pydantic import BaseModel
from qdrant_client import QdrantClient, models

from cloud.seed import to_server_sparse
from cloud.state import CloudState
from common.config import DENSE, FLEET_COLLECTION, QDRANT_URL, SPARSE
from common.embeddings import Embedder, index_text, point_id

app = FastAPI(title="FieldMind Sync API")
client = QdrantClient(url=QDRANT_URL)
embedder = Embedder()
state = CloudState()


class PushRequest(BaseModel):
    device: str
    note: dict
    base_version: int | None = None
def _upsert(pid, payload):
    text = index_text(payload)
    client.upsert(
        collection_name=FLEET_COLLECTION,
        points=[models.PointStruct(
            id=pid,
            vector={DENSE: embedder.dense_query(text), SPARSE: to_server_sparse(embedder.sparse_doc(text))},
            payload=payload,
        )],
        wait=True,
    )


def _add_knowledge(req):
    note = req.note
    payload = {**note, "doc_id": note["note_id"], "type": "field_note",
               "version": 1, "source_device": req.device}
    _upsert(point_id(note["note_id"]), payload)
    state.set_version(note["note_id"], 1, req.device)
    return {"status": "accepted"}


def _apply_edit(req, doc_id):
    current = state.version(doc_id)
    if current is None:
        return {"status": "rejected", "reason": f"unknown document {doc_id}"}
    if req.base_version != current:
        state.add_conflict(doc_id, req.note["note_id"], req.device,
                           req.base_version, current, req.note["text"])
        return {"status": "conflict", "doc_id": doc_id,
                "base_version": req.base_version, "server_version": current}

    existing = client.retrieve(FLEET_COLLECTION, ids=[point_id(doc_id)], with_payload=True)[0].payload
    new_version = current + 1
    payload = {**existing, "text": req.note["text"], "version": new_version,
               "updated_by": req.device, "source_note": req.note["note_id"]}
    _upsert(point_id(doc_id), payload)
    state.set_version(doc_id, new_version, req.device)
    return {"status": "applied_edit", "doc_id": doc_id, "version": new_version}
@app.get("/health")
def health():
    return {"status": "ok", "fleet_points": client.count(FLEET_COLLECTION).count}


@app.post("/push")
def push(req: PushRequest):
    note_id = req.note["note_id"]
    with state.lock:
        previous_outcome = state.received_outcome(note_id)
        if previous_outcome is not None:
            return {"status": previous_outcome, "replayed": True}
        doc_id = req.note.get("edits_doc_id")
        result = _apply_edit(req, doc_id) if doc_id else _add_knowledge(req)
        state.mark_received(note_id, req.device, result["status"])
        return result


@app.get("/conflicts")
def list_conflicts():
    items = state.conflicts()
    for c in items:
        records = client.retrieve(FLEET_COLLECTION, ids=[point_id(c["doc_id"])], with_payload=True)
        c["current_text"] = records[0].payload["text"] if records else ""
    return items


class ResolveRequest(BaseModel):
    action: str  # "keep_server" or "accept_proposed"


@app.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: int, req: ResolveRequest):
    with state.lock:
        c = state.get_conflict(conflict_id)
        if c is None or c["status"] != "open":
            return {"status": "not_found"}

        if req.action == "accept_proposed":
            existing = client.retrieve(FLEET_COLLECTION, ids=[point_id(c["doc_id"])], with_payload=True)[0].payload
            new_version = state.version(c["doc_id"]) + 1
            _upsert(point_id(c["doc_id"]), {
                **existing, "text": c["proposed_text"], "version": new_version,
                "updated_by": f"{c['device']} (approved by supervisor)", "source_note": c["note_id"],
            })
            state.set_version(c["doc_id"], new_version, "supervisor")
            state.set_conflict_status(conflict_id, "accepted")
            return {"status": "accepted", "version": new_version}

        state.set_conflict_status(conflict_id, "rejected")
        return {"status": "rejected"}

