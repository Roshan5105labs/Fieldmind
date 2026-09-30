# FieldMind

### Offline-first edge memory and intelligence for industrial field teams

**Code Cubicle 6.0 — PS3: AI-Powered Edge Memory & Intelligence Platform**

**Team:** Master Branch  
**Developer:** Roshan Pranao

---

## Overview

FieldMind is an offline-first knowledge and maintenance-memory platform built using **Qdrant Edge**.

Industrial technicians often work in environments where network connectivity is unreliable, latency matters, and sensitive information should not always leave the device. FieldMind gives every edge device its own persistent semantic memory, allowing technicians to search existing knowledge, record new fixes, and continue working even when the cloud is unavailable.

When connectivity returns, FieldMind intelligently decides which information should remain local, which requires review, and which should synchronize with centralized fleet knowledge.

The result is a complete **edge → cloud → edge knowledge lifecycle**, rather than simply running a local vector database.

---

## The Problem

Field teams commonly depend on centralized systems for:

- Maintenance manuals
- Historical work orders
- Fault-resolution knowledge
- Equipment-specific procedures
- Technician observations

However, these systems become difficult to use when:

- Network connectivity is intermittent or unavailable
- Cloud round trips introduce unnecessary latency
- Sensitive or site-specific information should remain local
- Multiple disconnected devices independently modify shared knowledge
- Bandwidth is constrained

FieldMind addresses these challenges by making knowledge available directly on the edge.

---

## Solution

Each FieldMind device maintains two local Qdrant Edge memory shards:

- **Fleet Memory** — synchronized organizational knowledge
- **Local Memory** — notes and discoveries created on the device

Users can search both memories completely offline using:

- Dense semantic retrieval
- BM25 sparse retrieval
- Reciprocal Rank Fusion (RRF)

New knowledge is immediately stored and searchable locally.

A policy engine then decides whether the information should:

- **Stay Local** — privacy-sensitive or site-specific information
- **Require Review** — unverified or low-confidence information
- **Synchronize** — verified knowledge useful across the fleet

Eligible records enter a persistent priority-aware outbox and synchronize when connectivity returns.

---

## Architecture

```text
┌───────────────────────────────┐
│         EDGE DEVICE A         │
│                               │
│  Local Embedding Model        │
│            ↓                  │
│       Qdrant Edge             │
│   ├── Fleet Memory            │
│   └── Local Memory            │
│            ↓                  │
│   Dense + BM25 + RRF          │
│            ↓                  │
│     Sync Policy Engine        │
│   ├── Keep Local              │
│   ├── Review                  │
│   └── Sync                    │
│            ↓                  │
│     Persistent Outbox         │
└──────────────┬────────────────┘
               │
        Intermittent Network
               │
               ▼
┌───────────────────────────────┐
│            CLOUD              │
│                               │
│      FastAPI Sync Layer       │
│            ↓                  │
│ Version + Conflict Metadata   │
│            ↓                  │
│        Qdrant Server          │
└──────────────┬────────────────┘
               │
      Full / Partial Snapshot
               │
               ▼
┌───────────────────────────────┐
│         EDGE DEVICE B         │
│                               │
│         Qdrant Edge           │
│       Fleet + Local Memory    │
└───────────────────────────────┘
```

---

## Key Features

### Offline Semantic Memory

FieldMind uses **Qdrant Edge** as persistent on-device vector memory.

After initial preparation, core device operations require no cloud access:

- Generate embeddings
- Search fleet knowledge
- Search local knowledge
- Record new notes
- Update local memory
- Apply synchronization policies
- Maintain the local outbox

### Hybrid Retrieval

FieldMind combines dense semantic retrieval and BM25 sparse retrieval with Reciprocal Rank Fusion.

This allows the system to handle both natural-language queries and operational identifiers such as:

```text
E417
MAN-CONV-01
WO-0012
```

### Intelligent Synchronization Policy

FieldMind evaluates each new record locally before synchronization.

```text
Personal information detected
        ↓
KEEP LOCAL

Site-specific information
        ↓
KEEP LOCAL

Unverified / low-confidence
        ↓
REVIEW

Verified fleet-wide fix
        ↓
SYNC — Priority 3

Verified document edit
        ↓
SYNC — Priority 2

Routine verified knowledge
        ↓
SYNC — Priority 1
```

Privacy rules execute before synchronization priority.

### Bandwidth-Aware Outbox

Synchronization is controlled through a persistent SQLite outbox.

Each record stores:

- Policy decision
- Reason
- Priority
- Payload size
- Base document version
- Synchronization status

A configurable byte budget determines how much data may be synchronized during a connection window. Records that do not fit remain safely queued.

### Cross-Device Knowledge Propagation

A repair discovered by one technician can become searchable knowledge on another device.

```text
Device A offline
      ↓
Technician records fix
      ↓
Immediately searchable locally
      ↓
Connectivity returns
      ↓
Synchronize with Qdrant Server
      ↓
Device B refreshes Fleet Memory
      ↓
Repair becomes searchable on Device B
```

### Version-Aware Conflict Handling

Disconnected devices may independently edit the same fleet document.

FieldMind avoids silent last-write-wins behavior through version-aware synchronization.

```text
Device A ── MAN-CONV-01 v1 ── Edit A
Device B ── MAN-CONV-01 v1 ── Edit B

A synchronizes
        ↓
Server becomes v2

B synchronizes using base_version = 1
        ↓
CONFLICT
```

The conflicting proposal is stored for explicit supervisor resolution.

### Idempotent Synchronization

Repeated synchronization requests do not create duplicate knowledge.

For example:

```text
Initial request
→ conflict

Retry same note_id
→ conflict
→ replayed = true
```

The original outcome is preserved on retry.

---

## Dashboard

The Streamlit dashboard allows users to inspect and control:

- Device online/offline state
- Hybrid knowledge search
- Search latency
- Fleet memory
- Local memory
- New field-note creation
- Policy decisions
- Persistent outbox
- Synchronization status
- Bandwidth budget
- Review queue
- Activity history
- Conflicts
- Conflict resolution
- Cloud knowledge status

---

## End-to-End Verified Workflow

The following workflow was tested successfully:

1. Device A receives its initial fleet snapshot.
2. Device A goes offline.
3. Existing knowledge remains searchable.
4. A technician records a new verified repair.
5. The repair becomes immediately searchable locally.
6. The repair enters the high-priority synchronization queue.
7. Device A reconnects.
8. The repair synchronizes to Qdrant Server.
9. Device B does not initially contain the repair.
10. Device B receives an incremental fleet snapshot.
11. Device B can now retrieve the repair locally.

---

## Runtime Verification

| Test | Result |
|---|---|
| Clean Docker build | ✅ PASS |
| Qdrant Server startup | ✅ PASS |
| Qdrant Edge startup | ✅ PASS |
| Offline dense search | ✅ PASS |
| Offline BM25 search | ✅ PASS |
| Offline note creation | ✅ PASS |
| Persistent local outbox | ✅ PASS |
| Exact-ID retrieval | ✅ PASS |
| Privacy policy | ✅ PASS |
| Priority/budget synchronization | ✅ PASS |
| Network failure recovery | ✅ PASS |
| Idempotent synchronization | ✅ PASS |
| Device A → Cloud → Device B | ✅ PASS |
| Partial snapshot synchronization | ✅ PASS |
| Conflict detection | ✅ PASS |
| Conflict resolution | ✅ PASS |
| Memory inspection | ✅ PASS |

---

## Prototype Measurements

On the small synthetic prototype dataset:

- **49 initial fleet records**
- 7 maintenance manuals
- 42 historical work orders
- Dense embedding dimension: **384**
- Warm local search observed around **5–14 ms**
- Initial full device snapshot: approximately **202 KB**
- Incremental snapshots in the tested sequence: approximately **102–106 KB**

These values are prototype measurements, not large-scale production benchmarks.

---

## Technology Stack

### Edge

- Qdrant Edge
- Python
- FastEmbed / BGE-small-en-v1.5
- BM25
- SQLite

### Cloud

- Qdrant Server
- FastAPI
- SQLite
- Uvicorn

### Interface

- Streamlit

### Infrastructure

- Docker
- Linux
- Python 3.12

---

## Project Structure

```text
Fieldmind/
├── common/
│   ├── config.py
│   └── embeddings.py
├── data/
│   ├── generate.py
│   └── corpus/
│       ├── fleet.json
│       └── field_notes.json
├── cloud/
│   ├── api.py
│   ├── seed.py
│   ├── state.py
│   └── docker-compose.yml
├── device/
│   ├── node.py
│   ├── outbox.py
│   └── policy.py
├── dashboard/
│   └── app.py
├── scripts/
│   └── sync_demo.py
├── setup_models.py
├── Dockerfile
├── start.sh
└── requirements.txt
```

---

## Running Locally

### 1. Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd Fieldmind
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it and install dependencies:

```bash
pip install -r requirements.txt
```

### 3. Prepare the embedding model

```bash
python setup_models.py
```

### 4. Start Qdrant Server

```bash
docker compose -f cloud/docker-compose.yml up -d
```

### 5. Seed cloud knowledge

```bash
python -m cloud.seed
```

### 6. Start FastAPI

```bash
uvicorn cloud.api:app --host 0.0.0.0 --port 8000
```

### 7. Start the dashboard

```bash
streamlit run dashboard/app.py
```

---

## Docker

FieldMind also supports running through the provided Docker configuration.

The container starts:

```text
Qdrant Server
      ↓
FastAPI Sync Service
      ↓
Cloud Seed / Restore
      ↓
Streamlit Dashboard
```

The application UI is exposed on port:

```text
7860
```

To force a deterministic demo reset on startup:

```bash
FIELDMIND_RESET_ON_START=true
```

Otherwise, existing cloud state is preserved when available.

---

## Current Limitations

FieldMind is a hackathon prototype rather than a production deployment.

Current limitations include:

- Runtime storage is not guaranteed to survive container recreation without persistent storage.
- Conflict resolution updates centralized knowledge but does not automatically remove every originating local proposed copy.
- Privacy detection currently focuses on configured patterns such as phone numbers and email addresses.
- The synchronization service uses a single-process consistency model.
- Distributed locking and cross-database transactional guarantees are outside the current prototype scope.
- Performance measurements come from the synthetic prototype dataset.

---

## Why FieldMind Is More Than a Local Vector Database

FieldMind manages the complete lifecycle of distributed edge knowledge:

```text
Remember locally
      ↓
Retrieve offline
      ↓
Learn offline
      ↓
Classify what may leave the device
      ↓
Queue under bandwidth constraints
      ↓
Synchronize when connectivity returns
      ↓
Detect conflicting knowledge
      ↓
Propagate validated knowledge to other devices
```

This transforms isolated field discoveries into resilient fleet-wide knowledge while preserving offline operation.

---

## Team

**Team Master Branch**

**Roshan Pranao**

Code Cubicle 6.0  
PS3 — AI-Powered Edge Memory & Intelligence Platform
