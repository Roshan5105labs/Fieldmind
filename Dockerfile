FROM qdrant/qdrant:v1.19.0 AS qdrant

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libunwind8 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

COPY --from=qdrant --chown=user /qdrant /home/user/qdrant

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .
RUN python setup_models.py

ENV QDRANT__STORAGE__STORAGE_PATH=/home/user/app/storage/qdrant_server \
    QDRANT__STORAGE__SNAPSHOTS_PATH=/home/user/app/storage/qdrant_snapshots \
    QDRANT__TELEMETRY_DISABLED=true

EXPOSE 7860
CMD ["bash", "start.sh"]
