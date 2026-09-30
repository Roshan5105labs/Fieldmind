import json
import random
from datetime import date, timedelta
from pathlib import Path

rng = random.Random(42)
OUT_DIR = Path("data/corpus")

ASSETS = {
    "CNC":   [("CNC-09", "CHN-01"), ("CNC-11", "CHN-01"), ("CNC-14", "PUN-02"), ("CNC-21", "PUN-02")],
    "PRESS": [("PRESS-04", "CHN-01"), ("PRESS-06", "PUN-02")],
    "CONV":  [("CONV-02", "CHN-01"), ("CONV-05", "PUN-02")],
    "PUMP":  [("PUMP-07", "CHN-01"), ("PUMP-12", "PUN-02")],
    "COMP":  [("COMP-01", "CHN-01"), ("COMP-03", "PUN-02")],
}

MANUALS = [
    ("MAN-CNC-01", "CNC", "Spindle thermal protection",
     "Alarm E417 trips when spindle winding temperature exceeds 85 degrees C. Check cooling fan operation, intake filters and the thermal sensor connector before replacing the motor."),
    ("MAN-CNC-02", "CNC", "Spindle vibration checks",
     "Alarm V310 indicates vibration above limit. Inspect tool holder seating and taper cleanliness first, then spindle bearings. Bearing replacement requires spindle removal."),
    ("MAN-PRESS-01", "PRESS", "Hydraulic system",
     "Normal operating pressure is 180 bar. Alarm H220 means pressure dropped below 150 bar during stroke. Inspect cylinder seals, oil level and filter condition."),
    ("MAN-CONV-01", "CONV", "Belt tensioning procedure",
     "Tension the belt to 1 percent elongation measured between marks 1 m apart. Under-tensioned belts slip under load and trigger alarm C050. Recheck tension after 48 hours of running."),
    ("MAN-CONV-02", "CONV", "Belt tracking",
     "Alarm C071 indicates the belt drifting off-center. Adjust idler alignment in small steps and observe tracking over several full belt rotations."),
    ("MAN-PUMP-01", "PUMP", "Coolant pump service",
     "Low flow with grinding noise, alarm P611, usually indicates impeller damage. Fit an inlet strainer to prevent debris. Mechanical seal leaks are reported as P615."),
    ("MAN-COMP-01", "COMP", "Air compressor alarms",
     "A120 high discharge temperature: check intake filter and cooler fins. A130 pressure not building: inspect the unloader valve and check for air leaks."),
]

FAULTS = [
    {"code": "E417", "type": "CNC", "symptoms": ["Spindle motor overheating after {m} minutes of running", "E417 thermal alarm during long cutting cycles"],
     "cause": "Cooling fan intake blocked by metal chips", "fix": "Cleaned fan intake and filter, verified airflow"},
    {"code": "E417", "type": "CNC", "symptoms": ["Spindle motor overheating shortly after warm-up", "E417 alarm while motor housing is cool to touch"],
     "cause": "Thermal sensor connector loose, giving false readings", "fix": "Reseated connector and secured with retaining clip"},
    {"code": "V310", "type": "CNC", "symptoms": ["Excessive spindle vibration at high RPM", "V310 vibration alarm and poor surface finish"],
     "cause": "Tool holder not seated correctly, dirty taper", "fix": "Cleaned taper and reseated tool holder"},
    {"code": "V310", "type": "CNC", "symptoms": ["Spindle vibration and noise increasing over weeks", "V310 alarm with audible bearing noise"],
     "cause": "Worn spindle bearing", "fix": "Replaced spindle bearings and rebalanced"},
    {"code": "E102", "type": "CNC", "symptoms": ["Controller lost communication with HMI panel", "E102 alarm, HMI screen frozen"],
     "cause": "Ethernet cable damaged near cabinet door hinge", "fix": "Replaced cable and rerouted away from hinge"},
    {"code": "H220", "type": "PRESS", "symptoms": ["Hydraulic pressure dropping during stroke", "H220 alarm, visible oil around cylinder"],
     "cause": "Worn seal on main cylinder causing leak", "fix": "Replaced cylinder seal kit"},
    {"code": "H221", "type": "PRESS", "symptoms": ["Press stroke slower than normal", "H221 alarm, hydraulic pump running hot"],
     "cause": "Hydraulic filter clogged, oil contaminated", "fix": "Replaced filter and flushed hydraulic oil"},
    {"code": "C050", "type": "CONV", "symptoms": ["Belt slipping under load", "C050 alarm when conveyor fully loaded"],
     "cause": "Belt tension too low", "fix": "Adjusted tensioner to procedure"},
    {"code": "C050", "type": "CONV", "symptoms": ["Belt slipping on incline section", "C050 alarm, drive roller surface shiny"],
     "cause": "Drive roller lagging worn smooth", "fix": "Replaced roller lagging"},
    {"code": "C071", "type": "CONV", "symptoms": ["Belt drifting to one side", "C071 tracking alarm"],
     "cause": "Idler roller misaligned after maintenance", "fix": "Realigned idler and verified tracking"},
    {"code": "P611", "type": "PUMP", "symptoms": ["Coolant pump grinding noise and low flow", "P611 alarm, coolant flow below limit"],
     "cause": "Impeller damaged by debris", "fix": "Replaced impeller and fitted inlet strainer"},
    {"code": "P615", "type": "PUMP", "symptoms": ["Coolant leaking from pump shaft", "P615 seal leak alarm"],
     "cause": "Worn mechanical seal", "fix": "Replaced mechanical seal"},
    {"code": "A120", "type": "COMP", "symptoms": ["Compressor high discharge temperature", "A120 alarm during afternoon shifts"],
     "cause": "Intake filter clogged and cooler fins dusty", "fix": "Replaced intake filter and cleaned cooler"},
    {"code": "A130", "type": "COMP", "symptoms": ["Compressor running but pressure not building", "A130 alarm, compressor never unloads"],
     "cause": "Unloader valve leaking", "fix": "Replaced unloader valve"},
]

def random_date():
    return (date(2026, 1, 1) + timedelta(days=rng.randint(0, 250))).isoformat()


def make_manuals():
    return [
        {
            "doc_id": doc_id, "type": "manual", "title": title,
            "site_id": None, "asset_id": None, "equipment_type": eq_type,
            "fault_code": None, "text": text,
            "verified": True, "author": "OEM", "created_at": "2025-12-01", "version": 1,
        }
        for doc_id, eq_type, title, text in MANUALS
    ]


def make_work_orders(per_fault=3):
    orders = []
    for fault in FAULTS:
        for _ in range(per_fault):
            asset, site = rng.choice(ASSETS[fault["type"]])
            symptom = rng.choice(fault["symptoms"]).format(m=rng.choice([15, 20, 25, 30, 40]))
            orders.append({
                "doc_id": f"WO-{len(orders) + 1:04d}", "type": "work_order", "title": None,
                "site_id": site, "asset_id": asset, "equipment_type": fault["type"],
                "fault_code": fault["code"],
                "text": f"{symptom}. Root cause: {fault['cause']}. Resolution: {fault['fix']}.",
                "verified": rng.random() < 0.85,
                "author": f"TECH-{rng.randint(101, 140)}",
                "created_at": random_date(), "version": 1,
            })
    return orders


FIELD_NOTES = [
    {"note_id": "FN-A1", "device": "device_a", "site_id": "CHN-01", "asset_id": "CNC-09", "equipment_type": "CNC",
     "fault_code": "E417", "kind": "fix", "verified": True, "confidence": "high", "site_specific": False, "edits_doc_id": None,
     "text": "E417 alarm every afternoon even with clean fan and good sensor. Root cause: electrical cabinet air conditioner failed, enclosure above 45 degrees C. Resolution: repaired cabinet AC and added a temperature check to the weekly round."},
    {"note_id": "FN-A2", "device": "device_a", "site_id": "CHN-01", "asset_id": "PUMP-07", "equipment_type": "PUMP",
     "fault_code": "P611", "kind": "observation", "verified": False, "confidence": "medium", "site_specific": False, "edits_doc_id": None,
     "text": "Pump grinding again. Replacement impeller ordered, vendor contact Suresh at +91 98765 43210 for delivery update."},
    {"note_id": "FN-A3", "device": "device_a", "site_id": "CHN-01", "asset_id": "CONV-02", "equipment_type": "CONV",
     "fault_code": None, "kind": "observation", "verified": True, "confidence": "high", "site_specific": True, "edits_doc_id": None,
     "text": "CONV-02 drive motor is behind the packing line fence. Access needs the fence key from security cabin 3 and a line stop permit."},
    {"note_id": "FN-A4", "device": "device_a", "site_id": "CHN-01", "asset_id": "PRESS-04", "equipment_type": "PRESS",
     "fault_code": None, "kind": "routine", "verified": True, "confidence": "high", "site_specific": False, "edits_doc_id": None,
     "text": "Weekly inspection of PRESS-04 completed. Oil level normal, no leaks found."},
    {"note_id": "FN-A5", "device": "device_a", "site_id": "CHN-01", "asset_id": "CONV-02", "equipment_type": "CONV",
     "fault_code": "C050", "kind": "edit", "verified": True, "confidence": "high", "site_specific": False, "edits_doc_id": "MAN-CONV-01",
     "text": "Tension the belt to 1.5 percent elongation measured between marks 1 m apart. 1 percent was not enough for loaded belts and they slipped with alarm C050. Recheck tension after 48 hours of running."},
    {"note_id": "FN-B1", "device": "device_b", "site_id": "PUN-02", "asset_id": "COMP-03", "equipment_type": "COMP",
     "fault_code": "A130", "kind": "fix", "verified": True, "confidence": "high", "site_specific": False, "edits_doc_id": None,
     "text": "Compressor pressure not building but unloader valve tested fine. Root cause: cracked air line fitting behind the dryer. Resolution: replaced fitting, pressure normal."},
    {"note_id": "FN-B2", "device": "device_b", "site_id": "PUN-02", "asset_id": "PUMP-12", "equipment_type": "PUMP",
     "fault_code": None, "kind": "observation", "verified": False, "confidence": "low", "site_specific": False, "edits_doc_id": None,
     "text": "Possible early bearing wear on PUMP-12, slight noise at startup. Not confirmed, needs a vibration check."},
    {"note_id": "FN-B3", "device": "device_b", "site_id": "PUN-02", "asset_id": "CONV-05", "equipment_type": "CONV",
     "fault_code": "C050", "kind": "edit", "verified": True, "confidence": "high", "site_specific": False, "edits_doc_id": "MAN-CONV-01",
     "text": "Tension the belt to 1 percent elongation measured between marks 1 m apart. Recheck tension after 24 hours instead of 48, belts on CONV-05 loosened within a day."},
]

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fleet = make_manuals() + make_work_orders()

    with open(OUT_DIR / "fleet.json", "w", encoding="utf-8") as f:
        json.dump(fleet, f, indent=2)
    with open(OUT_DIR / "field_notes.json", "w", encoding="utf-8") as f:
        json.dump(FIELD_NOTES, f, indent=2)

    manuals = sum(1 for r in fleet if r["type"] == "manual")
    orders = [r for r in fleet if r["type"] == "work_order"]
    verified = sum(1 for r in orders if r["verified"])
    print(f"fleet.json: {len(fleet)} records ({manuals} manuals, {len(orders)} work orders, {verified} verified)")
    for site in ("CHN-01", "PUN-02"):
        print(f"  {site}: {sum(1 for r in orders if r['site_id'] == site)} work orders")
    print(f"field_notes.json: {len(FIELD_NOTES)} demo notes")


if __name__ == "__main__":
    main()