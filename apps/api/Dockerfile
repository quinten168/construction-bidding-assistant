# CSI Bid Assistant — container image.
#
# IMPORTANT: build from the REPO ROOT (01_Summer_2026/) so the data dependencies are in context:
#   docker build -f 02_modules/bid_assistant/Dockerfile -t csi-bid-assistant .
#   docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... csi-bid-assistant
#
# The app reuses the Plan Reader's Chroma store + the master CSV, which live elsewhere in the repo,
# so we copy those slices in (preserving paths the code expects). The vector store is large; for a
# real deploy you'd likely mount it as a volume (or use a hosted vector DB) instead of baking it.

FROM python:3.11-slim

# system deps for sentence-transformers / chromadb
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# 1. dependencies first (better layer caching)
COPY 02_modules/bid_assistant/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# 2. application code
COPY 02_modules/bid_assistant/        ./02_modules/bid_assistant/

# 3. the data the tools read (preserve repo-relative paths)
COPY 02_modules/plan_reader/01_pipeline/                       ./02_modules/plan_reader/01_pipeline/
COPY 02_modules/plan_reader/06_chroma/                         ./02_modules/plan_reader/06_chroma/
COPY 02_modules/plan_reader/00_input/plans/plans_manifest.csv  ./02_modules/plan_reader/00_input/plans/plans_manifest.csv
COPY 01_data/2026-06-03_csi_bid_master.csv                     ./01_data/2026-06-03_csi_bid_master.csv

WORKDIR /app/02_modules/bid_assistant
EXPOSE 8000
# Railway/Heroku set $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
