---
title: FieldMind
emoji: 🧠
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# FieldMind

FieldMind is an offline-first edge knowledge and maintenance-memory demo built with Qdrant Edge.

The container preserves an existing cloud collection by default. Set
`FIELDMIND_RESET_ON_START=true` for a deterministic demo reset at startup. After changing
indexed fields, use that setting once or select **Reset demo** in the dashboard to rebuild
the fleet vectors.
