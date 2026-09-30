import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import streamlit as st

from cloud.seed import seed
from common.config import CORPUS_DIR, DEVICES, SYNC_API_URL
from common.embeddings import Embedder
from device.node import DeviceNode, OfflineError

st.set_page_config(page_title="FieldMind", layout="wide")

STRONG, PARTIAL = 0.75, 0.68


@st.cache_resource
def get_embedder():
    return Embedder()


@st.cache_resource
def get_nodes():
    return {d: DeviceNode(d, get_embedder()) for d in DEVICES}


@st.cache_data
def field_notes():
    return json.loads((CORPUS_DIR / "field_notes.json").read_text(encoding="utf-8"))
def flash(device_id, message, kind="success"):
    st.session_state[f"flash_{device_id}"] = (kind, message)


def show_flash(device_id):
    item = st.session_state.pop(f"flash_{device_id}", None)
    if item:
        kind, message = item
        getattr(st, kind)(message)


def reset_demo():
    nodes = get_nodes()
    for node in nodes.values():
        node.close()
    seed()
    for d in DEVICES:
        nodes[d] = DeviceNode(d, get_embedder(), reset=True)
        nodes[d].pull_fleet()


def cloud_status():
    try:
        health = requests.get(f"{SYNC_API_URL}/health", timeout=3).json()
        conflicts = requests.get(f"{SYNC_API_URL}/conflicts", timeout=3).json()
        return health, conflicts
    except requests.RequestException:
        return None, []


def strength(score):
    if score is None or score < PARTIAL:
        return "weak"
    return "strong" if score >= STRONG else "partial"

def search_tab(node, device_id):
    question = st.text_input("Ask this device", key=f"q_{device_id}",
                             placeholder="e.g. E417 alarm in the afternoon, cabinet too hot")
    if not question:
        return
    start = time.perf_counter()
    results = node.search(question, limit=5)
    ms = (time.perf_counter() - start) * 1000
    st.caption(f"{len(results)} results in {ms:.1f} ms, searched entirely on this device")

    best = max((r["dense_score"] or 0) for r in results) if results else 0
    if best < PARTIAL:
        st.warning("No reliable match on this device. Treat these results with caution.")

    for r in results:
        p = r["payload"]
        ident = p.get("doc_id") or p.get("note_id")
        score = r["dense_score"]
        score_text = f" ({score:.2f})" if score is not None else ""
        with st.container(border=True):
            st.markdown(f"**{ident}** · `{r['source']}` · {strength(score)} match{score_text}")
            st.write(p["text"])
            meta = [p.get("asset_id"), p.get("fault_code"), p.get("site_id")]
            st.caption(" · ".join(m for m in meta if m))
def log_tab(node, device_id, items):
    logged = {i["note_id"] for i in items}
    scripted = [n for n in field_notes() if n["device"] == device_id and n["note_id"] not in logged]
    if scripted:
        choice = st.selectbox("Scripted demo note", scripted, key=f"pick_{device_id}",
                              format_func=lambda n: f"{n['note_id']}: {n['text'][:60]}...")
        if st.button("Log this note", key=f"logpick_{device_id}"):
            _, d = node.log_note(choice)
            flash(device_id, f"Logged {choice['note_id']} → {d.action}: {d.reason}")
            st.rerun()

    with st.form(f"custom_{device_id}", clear_on_submit=True):
        st.markdown("**Write a new note**")
        text = st.text_area("What did you find?")
        c1, c2 = st.columns(2)
        asset = c1.text_input("Asset (e.g. CNC-09)")
        fault = c2.text_input("Fault code (e.g. E417)")
        kind = st.selectbox("Type", ["fix", "observation", "routine"])
        verified = st.checkbox("Verified", value=True)
        site_specific = st.checkbox("Site-specific information")
        if st.form_submit_button("Log note") and text.strip():
            note = {
                "note_id": f"FN-{device_id[-1].upper()}-{int(time.time())}",
                "device": device_id, "site_id": node.site_id,
                "asset_id": asset or None, "equipment_type": None, "fault_code": fault or None,
                "kind": kind, "verified": verified, "confidence": "high" if verified else "low",
                "site_specific": site_specific, "edits_doc_id": None, "text": text.strip(),
            }
            _, d = node.log_note(note)
            flash(device_id, f"Logged {note['note_id']} → {d.action}: {d.reason}")
            st.rerun()

def outbox_tab(node, device_id, items, budget):
    b1, b2 = st.columns(2)
    if b1.button("Sync now", key=f"sync_{device_id}", type="primary", disabled=not node.online):
        try:
            s = node.sync_now(budget_bytes=budget)
            message = (f"Sent {s['sent']} · deferred {s['deferred']} · "
                       f"conflicts {s['conflicts']} · {s['bytes']} B of {budget} B budget")
            if s["status"] == "failed":
                flash(device_id, f"Sync failed for {s['failed']}: {s['error']}. {message}", "error")
            else:
                flash(device_id, message)
        except (OfflineError, requests.RequestException) as e:
            flash(device_id, f"Sync failed: {e}", "error")
        st.rerun()
    if b2.button("Pull fleet updates", key=f"pull_{device_id}", disabled=not node.online):
        try:
            r = node.pull_fleet()
            flash(device_id, f"Pulled {r['mode']} snapshot ({r['bytes'] / 1024:.0f} KB)")
        except (OfflineError, requests.RequestException) as e:
            flash(device_id, f"Pull failed: {e}", "error")
        st.rerun()

    if not items:
        st.caption("No notes logged on this device yet.")
    for item in items:
        with st.container(border=True):
            st.markdown(f"**{item['note_id']}** · `{item['status']}` · "
                        f"priority {item['priority']} · {item['size_bytes']} B")
            st.caption(item["reason"])
            if item["status"] == "needs_review":
                if st.button("Approve for sync (supervisor)", key=f"approve_{device_id}_{item['note_id']}"):
                    node.approve(item["note_id"])
                    flash(device_id, f"{item['note_id']} approved and queued for sync")
                    st.rerun()

def device_panel(device_id, budget):
    node = get_nodes()[device_id]
    st.subheader(node.label)
    st.caption(f"Site {node.site_id}")
    node.online = st.toggle("Connected to cloud", value=True, key=f"online_{device_id}")
    if node.online:
        st.markdown("🟢 **Online**")
    else:
        st.markdown("🔴 **Offline**: search and logging still work on this device")

    show_flash(device_id)

    items = node.outbox.items()
    count = lambda s: sum(1 for i in items if i["status"] == s)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Pending", count("pending"))
    m2.metric("Synced", count("synced"))
    m3.metric("Kept local", count("kept_local"))
    m4.metric("Review / conflict", count("needs_review") + count("conflict"))

    t_search, t_log, t_memory, t_outbox, t_activity = st.tabs(
        ["Search", "Log note", "Memory", "Outbox & sync", "Activity"]
    )
    with t_search:
        search_tab(node, device_id)
    with t_log:
        log_tab(node, device_id, items)
    with t_memory:
        memory = node.memory_records(limit=100)
        if memory:
            st.dataframe(memory, use_container_width=True, hide_index=True)
        else:
            st.caption("No records stored on this device.")
    with t_outbox:
        outbox_tab(node, device_id, items, budget)
    with t_activity:
        for a in node.outbox.activity(limit=30):
            st.text(f"{a['ts'][11:]}  {a['event']:10} {a['detail']}")

if any(node.fleet is None for node in get_nodes().values()):
    with st.spinner("Preparing demo devices..."):
        reset_demo()
with st.sidebar:
    st.title("FieldMind")
    st.caption("Offline-first maintenance memory on Qdrant Edge")
    budget = st.slider("Sync bandwidth budget (bytes)", 300, 3000, 1100, step=100)
    if st.button("Reset demo"):
        with st.spinner("Reseeding cloud and resetting both devices..."):
            reset_demo()
        st.success("Demo reset")

    health, conflicts = cloud_status()
    st.subheader("Cloud")
    if health:
        st.metric("Fleet knowledge records", health["fleet_points"])
        st.metric("Open conflicts", len(conflicts))
    else:
        st.error("Sync API unreachable. Is uvicorn running?")
st.info("Public shared demo: all visitors see the same two devices. "
        "Use **Reset demo** in the sidebar to start from a clean state.")
col_a, col_b = st.columns(2)
with col_a:
    device_panel("device_a", budget)
with col_b:
    device_panel("device_b", budget)

st.divider()
st.subheader("Cloud: conflicts awaiting a supervisor")
if not conflicts:
    st.caption("No open conflicts.")
for c in conflicts:
    with st.container(border=True):
        st.markdown(f"**{c['doc_id']}**: {c['device']} edited version {c['base_version']}, "
                    f"but the server was already at version {c['server_version']}.")
        left, right = st.columns(2)
        left.markdown("**Current server version**")
        left.write(c["current_text"])
        right.markdown(f"**Proposed by {c['device']}**")
        right.write(c["proposed_text"])
        k1, k2 = st.columns(2)
        for col, action, label in ((k1, "keep_server", "Keep server version"),
                                   (k2, "accept_proposed", "Accept proposed edit")):
            if col.button(label, key=f"{action}_{c['id']}"):
                requests.post(f"{SYNC_API_URL}/conflicts/{c['id']}/resolve",
                              json={"action": action}, timeout=10)
                st.rerun()

