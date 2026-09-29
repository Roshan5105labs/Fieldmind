import re
from dataclasses import dataclass

SYNC = "sync"
LOCAL = "keep_local"
REVIEW = "review"

PHONE_RE = re.compile(r"\+?\d[\d\s\-]{7,}\d")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


@dataclass
class Decision:
    action: str
    reason: str
    priority: int = 0


def find_personal_data(text):
    found = []
    for match in PHONE_RE.finditer(text):
        if sum(c.isdigit() for c in match.group()) >= 10:
            found.append("phone number")
            break
    if EMAIL_RE.search(text):
        found.append("email address")
    return found


def decide(record):
    personal = find_personal_data(record["text"])
    if personal:
        return Decision(LOCAL, f"Contains personal data ({', '.join(personal)}); must not leave the device")

    if record.get("site_specific"):
        return Decision(LOCAL, "Site-specific access details; only useful at this site")

    if not record.get("verified") or record.get("confidence") == "low":
        return Decision(REVIEW, "Unverified observation; needs supervisor confirmation before sharing")

    kind = record.get("kind")
    if kind == "fix":
        return Decision(SYNC, "Verified new fix; useful to technicians at every site", priority=3)
    if kind == "edit":
        return Decision(SYNC, f"Verified correction to fleet document {record.get('edits_doc_id')}", priority=2)
    return Decision(SYNC, "Verified routine record; low value to other sites", priority=1)


if __name__ == "__main__":
    import json
    from common.config import CORPUS_DIR

    notes = json.loads((CORPUS_DIR / "field_notes.json").read_text(encoding="utf-8"))
    for note in notes:
        d = decide(note)
        print(f"{note['note_id']:6} {d.action:10} p={d.priority}  {d.reason}")