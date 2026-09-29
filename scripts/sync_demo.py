import json

import requests

from cloud.seed import seed
from common.config import CORPUS_DIR, SYNC_API_URL
from common.embeddings import Embedder
from device.node import DeviceNode


def banner(text):
    print(f"\n=== {text} ===")


def show(node, question):
    print(f"\n[{node.label}] Q: {question}")
    for r in node.search(question, limit=3):
        p = r["payload"]
        ident = p.get("doc_id") or p.get("note_id")
        print(f"  [{r['source']:11}] {ident}: {p['text'][:55]}...")


def main():
    banner("Reset the cloud")
    seed()

    embedder = Embedder()
    a = DeviceNode("device_a", embedder, reset=True)
    b = DeviceNode("device_b", embedder, reset=True)
    print("A pull:", a.pull_fleet())
    print("B pull:", b.pull_fleet())

    banner("Both devices go offline and log notes")
    a.online = b.online = False
    notes = json.loads((CORPUS_DIR / "field_notes.json").read_text(encoding="utf-8"))
    for note in notes:
        (a if note["device"] == "device_a" else b).log_note(note)
    for node in (a, b):
        for item in node.outbox.items():
            print(f"  {node.label} {item['note_id']:6} {item['status']:13} "
                  f"{item['size_bytes']:4} B  {item['reason']}")

    banner("Device A reconnects with a 1100-byte budget")
    a.online = True
    print(a.sync_now(budget_bytes=1100))

    banner("Device B reconnects and syncs")
    b.online = True
    print(b.sync_now())

    banner("Device B pulls fleet updates")
    print(b.pull_fleet())
    show(b, "E417 alarm in the afternoon, cabinet too hot")

    banner("Device A syncs its remaining notes, no budget")
    print(a.sync_now())

    banner("Open conflicts on the server")
    for c in requests.get(f"{SYNC_API_URL}/conflicts", timeout=10).json():
        print(f"  {c['doc_id']}: {c['device']} edited v{c['base_version']}, "
              f"server is at v{c['server_version']}")
        print(f"    proposed: {c['proposed_text'][:70]}...")

    a.close()
    b.close()


if __name__ == "__main__":
    main()