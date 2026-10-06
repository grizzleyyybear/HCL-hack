# InsightDesk image: one image runs both the API (default CMD) and the Streamlit UI (compose overrides CMD).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    HF_HOME=/home/app/.cache/huggingface \
    ANONYMIZED_TELEMETRY=False

WORKDIR /app

# CPU-only torch first: the default Linux wheel pulls several GB of CUDA libraries we never use.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

# Non-root user (uid 1000 matches most Linux hosts, so the ./data bind mount stays writable).
# /data is created here so the named volume mounted there inherits this owner.
RUN useradd --create-home --uid 1000 app && mkdir /data && chown app:app /app /data

COPY --chown=app:app . .
USER app

# Download the embedding model at build time so the first request does not wait for it.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

EXPOSE 8000 8501
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
