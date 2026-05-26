# syntax=docker/dockerfile:1.7
# =============================================================================
# Stage 1: Builder — compile Python wheels
# =============================================================================
FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Build tools (only in this stage, not in final image)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gcc g++ python3-dev \
      libsndfile1-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

# CPU-only PyTorch saves ~2.3 GB vs full CUDA build
# BuildKit cache mount keeps pip cache between builds without adding to image size
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user --no-warn-script-location \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      -r requirements.txt

# =============================================================================
# Stage 2: Runtime — lean image, no build tools
# =============================================================================
FROM python:3.12-slim-bookworm AS runtime

# Runtime system libs only
RUN apt-get update && apt-get install -y --no-install-recommends \
      libsndfile1 ffmpeg libgomp1 libpq5 curl \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Non-root user (uid/gid 1000)
RUN groupadd -r app --gid 1000 && \
    useradd -r -g app --uid 1000 -m -d /home/app -s /bin/bash app

WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder --chown=app:app /root/.local /home/app/.local

ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    # HuggingFace cache → named volume (hf_cache)
    HF_HOME=/models/huggingface \
    TRANSFORMERS_CACHE=/models/huggingface \
    # Essentia models → bind mount (models_cache/)
    ESSENTIA_MODEL_CACHE=/app/models_cache

# Directories the app writes to at runtime
RUN mkdir -p /models/huggingface /app/models_cache /app/logs && \
    chown -R app:app /models /app/models_cache /app/logs

# Copy app code last to maximise layer cache reuse
COPY --chown=app:app . /app

USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
