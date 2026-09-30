#!/bin/bash
set -e
mkdir -p storage

cd /home/user/qdrant && ./qdrant &
cd /home/user/app
until curl -s http://localhost:6333/healthz > /dev/null; do sleep 1; done
echo "Qdrant is up"

uvicorn cloud.api:app --host 127.0.0.1 --port 8000 &
until curl -s http://localhost:8000/docs > /dev/null; do sleep 1; done
echo "Sync API is up"

python -m cloud.seed

exec streamlit run dashboard/app.py \
    --server.port 7860 --server.address 0.0.0.0 --server.headless true