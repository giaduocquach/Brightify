# PLAN 3 — ĐÓNG GÓI DOCKER TOÀN HỆ THỐNG BRIGHTIFY

**Ngày tạo:** 2026-05-26
**Phạm vi:** Đóng gói toàn bộ stack Brightify vào Docker — bao gồm chuyển PostgreSQL từ local sang Docker container. Cover dev/staging/production environments.

> **Trạng thái hiện tại:** DB chạy local PostgreSQL trên máy host; app chạy uvicorn local. Không có Dockerfile, không có docker-compose, không có deployment automation. CLAUDE.md không document deployment workflow.

---

## MỤC LỤC

1. [Mục tiêu & nguyên tắc](#1-mục-tiêu--nguyên-tắc)
2. [Kiến trúc tổng thể](#2-kiến-trúc-tổng-thể)
3. [Phân tích phụ thuộc](#3-phân-tích-phụ-thuộc)
4. [Dockerfile cho app](#4-dockerfile-cho-app)
5. [PostgreSQL + pgvector container](#5-postgresql--pgvector-container)
6. [docker-compose tổng](#6-docker-compose-tổng)
7. [**Data Layout & Persistence (Master Guide)**](#7-data-layout--persistence-master-guide) ⭐
8. [Secrets & cấu hình](#8-secrets--cấu-hình)
9. [Nginx reverse proxy & SSL](#9-nginx-reverse-proxy--ssl)
10. [Migration & seed flow](#10-migration--seed-flow)
11. [Production hardening + Backup & Restore](#11-production-hardening)
12. [Multi-environment (dev/staging/prod)](#12-multi-environment-devstagingprod)
13. [CI/CD pipeline](#13-cicd-pipeline)
14. [Monitoring & logging](#14-monitoring--logging)
15. [Migration + Production Deploy Runbook](#15-migration-steps-từ-hiện-tại)
16. [Checklist & success criteria](#16-checklist--success-criteria)
17. [Tài liệu tham khảo](#17-tài-liệu-tham-khảo)

---

## 1. MỤC TIÊU & NGUYÊN TẮC

### 1.1 Mục tiêu

1. **Reproducibility** — `docker compose up` → toàn bộ stack chạy được trên máy bất kỳ (Linux/macOS/Windows + Docker Desktop).
2. **Isolation** — DB không expose ra Internet; secrets không leak; dev/prod tách biệt.
3. **Performance** — image final ≤ 3 GB; cold start ≤ 90s; PostgreSQL với HNSW pgvector tuning đúng.
4. **Production-ready** — non-root user, healthcheck, resource limits, structured logging, secrets management.
5. **Developer DX** — Hot reload trong dev, debugger attachable, log dễ đọc.
6. **No regression** — Mọi feature hiện tại hoạt động sau Docker hóa.

### 1.2 Nguyên tắc

1. **Multi-stage build** — giảm image size.
2. **CPU-only PyTorch** — không bundle CUDA libs (~2GB saving).
3. **Named volumes cho DB** — performance ổn định.
4. **Bind mounts cho dataset lớn** — không copy 50GB MP3 vào image.
5. **Init scripts cho extensions** — pgvector, pg_trgm tự động.
6. **Healthchecks chuẩn** — `depends_on: condition: service_healthy`.
7. **Non-root user** — UID 1000, giảm attack surface.
8. **Secrets qua `/run/secrets/`** ở production, `.env` ở dev.
9. **Version pinning** — không dùng `latest` tag.

---

## 2. KIẾN TRÚC TỔNG THỂ

### 2.1 Sơ đồ services

```
┌─────────────────────────────────────────────────────────────────┐
│                       DOCKER COMPOSE STACK                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────────┐                                              │
│   │   nginx      │ ← public ports 80, 443                       │
│   │  (reverse    │                                              │
│   │   proxy +SSL)│                                              │
│   └──────┬───────┘                                              │
│          │ frontend network                                     │
│          ↓                                                      │
│   ┌──────────────┐                                              │
│   │     app      │ ← FastAPI, uvicorn, 1 worker/container       │
│   │  (Brightify) │   models: PhoBERT, CLIP, MERT (Pillar A)     │
│   │              │   volumes: music_files (ro), HF cache, etc.  │
│   └──────┬───────┘                                              │
│          │ backend network (internal)                           │
│          ↓                                                      │
│   ┌──────────────┐    ┌──────────────────┐                      │
│   │     db       │    │   redis (option) │                      │
│   │  pgvector/pg17│   │   cache + rate   │                      │
│   │              │    │   limit          │                      │
│   └──────────────┘    └──────────────────┘                      │
│                                                                 │
│   ┌──────────────┐                                              │
│   │   migrate    │ ← one-shot Alembic upgrade head              │
│   │   (sidecar)  │                                              │
│   └──────────────┘                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Volumes:
  postgres_data       — DB persistence (named)
  hf_cache            — HuggingFace model cache (named)
  essentia_cache      — Essentia .pb files (named or bind)
  redis_data          — Redis persistence (named, optional)
  ./music_files:ro    — MP3 dataset (bind mount, read-only)
  ./album_art:ro      — Album art (bind, ro)
  ./artist_images:ro  — Artist images (bind, ro)
  ./checkpoints:ro    — Pipeline checkpoints (bind, ro)

Networks:
  frontend  — public-facing (nginx only)
  backend   — internal (db, redis, app)
```

### 2.2 Services overview

| Service | Image | Phụ thuộc | Ports | Volumes |
|---|---|---|---|---|
| `nginx` | `nginx:1.27-alpine` | app | 80, 443 | nginx.conf, certs, static |
| `app` | Custom (Brightify) | db (healthy), migrate (success) | 8000 (internal) | music, art, HF, essentia cache |
| `migrate` | Custom (same as app) | db (healthy) | — | (none) |
| `db` | `pgvector/pgvector:pg17` | — | 5432 (internal) | postgres_data, init scripts |
| `redis` | `redis:7-alpine` | — | 6379 (internal) | redis_data |
| `worker` (optional) | Custom (same as app) | db, redis | — | (background jobs) |

### 2.3 File structure

```
GR2-main/
├── Dockerfile                          # App image
├── docker-compose.yml                  # Base config
├── docker-compose.dev.yml              # Dev overrides (hot reload, debug)
├── docker-compose.prod.yml             # Prod overrides (limits, secrets)
├── .dockerignore
├── .env.example                        # Already exists; add Docker vars
├── .env                                # Local (gitignored)
├── nginx/
│   ├── nginx.conf
│   ├── certs/                          # Let's Encrypt mount
│   └── www/                            # ACME challenge
├── db/
│   ├── init/
│   │   └── 01-extensions.sql           # CREATE EXTENSION vector, pg_trgm
│   └── ...
├── secrets/                            # Prod only, gitignored
│   ├── db_password.txt
│   ├── admin_key.txt
│   └── redis_password.txt
└── scripts/
    ├── docker-entrypoint.sh            # App startup script
    ├── wait-for-db.sh                  # (optional fallback)
    └── backup-db.sh                    # Cron backup
```

---

## 3. PHÂN TÍCH PHỤ THUỘC

### 3.1 System-level dependencies

| Dependency | Purpose | Image install |
|---|---|---|
| `libsndfile1` | librosa audio I/O | `apt-get install -y libsndfile1` |
| `ffmpeg` | yt-dlp download, audio conversion | `apt-get install -y ffmpeg` |
| `libgomp1` | OpenMP runtime for TF, Essentia | `apt-get install -y libgomp1` |
| `curl` | healthcheck | `apt-get install -y curl` |
| `build-essential` | C compilation cho pip wheels | `apt-get install -y build-essential` (chỉ ở builder stage) |

### 3.2 Python packages (key)

| Package | Size impact | Notes |
|---|---|---|
| `torch` | ~2.5 GB (full) / ~200 MB (CPU-only) | Dùng `--extra-index-url https://download.pytorch.org/whl/cpu` |
| `transformers` | ~400 MB (with deps) | PhoBERT, CLIP, MERT (sau Pillar A) |
| `essentia-tensorflow` | ~300 MB | Audio ML models |
| `librosa` | ~50 MB | DSP |
| `pgvector`, `sqlalchemy[asyncio]`, `asyncpg` | ~20 MB | DB |
| `Pillow` | ~10 MB | Image processing |
| `yt-dlp` | ~5 MB | Pipeline phase 3 |

### 3.3 Model weights (downloaded at runtime)

| Model | Size | Source | Volume mount |
|---|---|---|---|
| PhoBERT-base-v2 | ~500 MB | HuggingFace | `hf_cache` |
| CLIP ViT-B/32 | ~600 MB | HuggingFace | `hf_cache` |
| MERT-v1-95M (Pillar A) | ~340 MB | HuggingFace | `hf_cache` |
| LAION CLAP music (Pillar A) | ~700 MB | HuggingFace | `hf_cache` |
| Essentia EffNet-Discogs | ~80 MB | MTG | `essentia_cache` |
| DEAM V-A regressor | ~30 MB | MTG | `essentia_cache` |
| MSD-MusiCNN | ~20 MB | MTG | `essentia_cache` |
| TempoCNN | ~10 MB | MTG | `essentia_cache` |

**Total models:** ~2.3 GB. Mount qua named volume → tránh re-download mỗi rebuild.

### 3.4 Dataset (host bind mount)

| Directory | Estimated size | Mount type |
|---|---|---|
| `music_files/` | 10-50 GB | bind, `:ro` |
| `album_art/` | 1-2 GB | bind, `:ro` |
| `artist_images/` | 200-500 MB | bind, `:ro` |
| `checkpoints/` | 100-500 MB | bind, `:ro` |
| `data/*.csv`, `*.npy` | ~200 MB | copy vào image hoặc bind |

---

## 4. DOCKERFILE CHO APP

### 4.1 Multi-stage Dockerfile

```dockerfile
# syntax=docker/dockerfile:1.7
# =============================================================================
# Stage 1: Builder — compile Python wheels
# =============================================================================
FROM python:3.10-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Build tools - chỉ tồn tại ở stage này
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gcc g++ python3-dev \
      libsndfile1-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

# BuildKit cache mount — không tăng image size, accelerate rebuild
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user --no-warn-script-location \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      -r requirements.txt

# =============================================================================
# Stage 2: Runtime
# =============================================================================
FROM python:3.10-slim-bookworm AS runtime

# Runtime libs (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libsndfile1 ffmpeg libgomp1 libpq5 curl \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Non-root user
RUN groupadd -r app --gid 1000 && \
    useradd -r -g app --uid 1000 -m -d /home/app -s /bin/bash app

WORKDIR /app

# Copy Python packages từ builder
COPY --from=builder --chown=app:app /root/.local /home/app/.local

ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models/huggingface \
    TRANSFORMERS_CACHE=/models/huggingface \
    ESSENTIA_MODEL_CACHE=/app/models_cache

# Tạo directories cần thiết với đúng owner
RUN mkdir -p /models/huggingface /app/models_cache /app/logs && \
    chown -R app:app /models /app/models_cache /app/logs

# Copy app code (layer changes most, đặt cuối để tận dụng cache)
COPY --chown=app:app . /app

# Switch sang non-root
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

EXPOSE 8000

# Default command — uvicorn 1 worker (model load 1 lần)
CMD ["uvicorn", "app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
```

### 4.2 .dockerignore

```
# Virtual envs & caches
.venv/
venv/
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
.hypothesis/

# Large data — bind mount ở runtime (xem §7)
music_files/
album_art/
artist_images/
models_cache/
checkpoints/
data/*.npy
data/*.parquet
var/                # canonical runtime data root
logs/
*.log

# Git & IDE
.git/
.github/workflows/  # giữ workflows ngoài image
.gitignore
.gitattributes
.vscode/
.idea/
*.swp

# Secrets
.env
.env.*
!.env.example
secrets/

# Docs & tests
docs/
test/
*.md
!README.md

# Docker meta
Dockerfile*
docker-compose*.yml
.dockerignore

# OS
.DS_Store
Thumbs.db

# Backup
*.bak
*.bak~
*.tmp
db/models.py.bak
```

### 4.3 Tối ưu image size

| Optimization | Saving |
|---|---|
| `python:3.10-slim` thay vì `python:3.10` | ~700 MB |
| Multi-stage (remove build-essential, gcc) | ~500 MB |
| CPU-only PyTorch | ~2,300 MB |
| `apt-get clean` + `rm -rf /var/lib/apt/lists/*` | ~50 MB |
| `.dockerignore` đầy đủ | varies |
| Models trong volume (không vào image) | ~2,300 MB |

**Expected final image size:** ~1.5-2.5 GB (so với ~8 GB nếu không tối ưu).

### 4.4 Verify build

```bash
docker build -t brightify:dev .
docker images brightify:dev   # check size

# Test run với placeholder env
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql://test \
  -e BRIGHTIFY_ADMIN_KEY=test \
  brightify:dev

# Inspect layers
docker history brightify:dev
```

---

## 5. POSTGRESQL + PGVECTOR CONTAINER

### 5.1 Image lựa chọn

**Khuyến nghị: `pgvector/pgvector:pg17`** (upstream image, pre-install extension).

Variant alternatives:
- `pgvector/pgvector:pg17-trixie` — newer Debian Trixie base.
- `pgvector/pgvector:pg16` — nếu cần Postgres 16.

**Không khuyến nghị:** image cộng đồng cũ (`ankane/pgvector` đã ngưng update).

### 5.2 Init scripts

PostgreSQL Docker entrypoint chạy file trong `/docker-entrypoint-initdb.d/` chỉ vào lần đầu tiên (khi volume trống).

```sql
-- db/init/01-extensions.sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

```sql
-- db/init/02-tuning.sql (optional, nếu không pass qua command)
ALTER SYSTEM SET shared_buffers = '2GB';
ALTER SYSTEM SET maintenance_work_mem = '1GB';
ALTER SYSTEM SET max_parallel_maintenance_workers = 2;
ALTER SYSTEM SET effective_cache_size = '4GB';
ALTER SYSTEM SET work_mem = '64MB';
```

**Lưu ý:** Pattern dùng `command:` trong compose linh hoạt hơn `ALTER SYSTEM` (không cần restart).

### 5.3 Memory tuning cho HNSW

Brightify dùng 768-dim embeddings × 4,300 songs. HNSW index khoảng:

```
size = n_vectors × (dim × 4 bytes + m × 8 bytes) × overhead
     = 4,300 × (768 × 4 + 16 × 8) × 1.2
     ≈ 4,300 × 3,200 × 1.2
     ≈ 16 MB (rất nhỏ)
```

Index nhỏ → fit trong `shared_buffers` dễ dàng. Nhưng `maintenance_work_mem` cần đủ cho **build time**.

**Cấu hình khuyến nghị (cho host 8GB+ RAM):**

| Parameter | Value | Lý do |
|---|---|---|
| `shared_buffers` | 2GB | 25% RAM container |
| `effective_cache_size` | 4GB | 50% RAM hint |
| `maintenance_work_mem` | 1GB | HNSW build, GIN trigram |
| `work_mem` | 64MB | Per-query memory |
| `max_parallel_maintenance_workers` | 2 | HNSW parallel build |
| `max_connections` | 50 | App pool 30 + buffer |

### 5.4 shm_size

Parallel HNSW workers chia sẻ memory qua `/dev/shm`. Mặc định Docker = 64MB → OOM khi build index lớn.

```yaml
shm_size: 2gb   # ≥ maintenance_work_mem
```

### 5.5 Service definition

```yaml
db:
  image: pgvector/pgvector:pg17
  container_name: brightify_db
  restart: unless-stopped
  shm_size: 2gb
  environment:
    POSTGRES_USER: ${POSTGRES_USER}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    POSTGRES_DB: ${POSTGRES_DB}
    PGDATA: /var/lib/postgresql/data/pgdata
  command:
    - "postgres"
    - "-c"
    - "shared_buffers=2GB"
    - "-c"
    - "effective_cache_size=4GB"
    - "-c"
    - "maintenance_work_mem=1GB"
    - "-c"
    - "max_parallel_maintenance_workers=2"
    - "-c"
    - "work_mem=64MB"
    - "-c"
    - "max_connections=50"
    - "-c"
    - "log_min_duration_statement=1000"   # log slow queries > 1s
  volumes:
    - postgres_data:/var/lib/postgresql/data
    - ./db/init:/docker-entrypoint-initdb.d:ro
    - ./logs/postgres:/var/log/postgresql
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 30s
  networks:
    - backend
  deploy:
    resources:
      limits:
        memory: 4G
        cpus: '2.0'
      reservations:
        memory: 2G
```

### 5.6 Backup strategy

```bash
# scripts/backup-db.sh
#!/bin/bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="brightify_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

docker compose exec -T db pg_dump \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  --no-owner --clean --if-exists \
  | gzip > "$BACKUP_DIR/$FILENAME"

# Keep last 7 days
find "$BACKUP_DIR" -name "brightify_*.sql.gz" -mtime +7 -delete
```

Cron entry:
```
0 3 * * * cd /opt/brightify && bash scripts/backup-db.sh >> logs/backup.log 2>&1
```

---

## 6. DOCKER-COMPOSE TỔNG

### 6.1 Base `docker-compose.yml`

```yaml
name: brightify

x-app-base: &app-base
  build:
    context: .
    dockerfile: Dockerfile
    args:
      BUILDKIT_INLINE_CACHE: 1
  environment:
    DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
    REDIS_URL: redis://redis:6379/0
    ALLOWED_ORIGINS: ${ALLOWED_ORIGINS:-http://localhost,https://localhost}
    BRIGHTIFY_ADMIN_KEY: ${BRIGHTIFY_ADMIN_KEY}
    HF_HOME: /models/huggingface
    TRANSFORMERS_CACHE: /models/huggingface
    ESSENTIA_MODEL_CACHE: /app/models_cache
    PYTHONUNBUFFERED: "1"
    LOG_LEVEL: ${LOG_LEVEL:-INFO}

services:
  # =========================================================================
  # Database
  # =========================================================================
  db:
    image: pgvector/pgvector:pg17
    container_name: brightify_db
    restart: unless-stopped
    shm_size: 2gb
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      PGDATA: /var/lib/postgresql/data/pgdata
    command:
      - postgres
      - -c
      - shared_buffers=2GB
      - -c
      - effective_cache_size=4GB
      - -c
      - maintenance_work_mem=1GB
      - -c
      - max_parallel_maintenance_workers=2
      - -c
      - work_mem=64MB
      - -c
      - max_connections=50
      - -c
      - log_min_duration_statement=1000
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks:
      - backend

  # =========================================================================
  # Redis (cache + rate limiter)
  # =========================================================================
  redis:
    image: redis:7-alpine
    container_name: brightify_redis
    restart: unless-stopped
    command: >
      redis-server
      --appendonly yes
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    networks:
      - backend

  # =========================================================================
  # Migration (one-shot)
  # =========================================================================
  migrate:
    <<: *app-base
    container_name: brightify_migrate
    command: alembic upgrade head
    depends_on:
      db:
        condition: service_healthy
    restart: "no"
    networks:
      - backend

  # =========================================================================
  # Main app
  # =========================================================================
  app:
    <<: *app-base
    container_name: brightify_app
    expose:
      - "8000"
    volumes:
      # Read-only dataset bind mounts (paths từ .env, xem §7.4)
      - ${MUSIC_FILES_PATH:-./music_files}:/app/music_files:ro
      - ${ALBUM_ART_PATH:-./album_art}:/app/album_art:ro
      - ${ARTIST_IMAGES_PATH:-./artist_images}:/app/artist_images:ro
      - ${CHECKPOINTS_PATH:-./checkpoints}:/app/checkpoints:ro
      - ${PROCESSED_PATH:-./data}:/app/data:ro
      - ${ESSENTIA_MODELS_PATH:-./models_cache}:/app/models_cache:ro
      - ${ANNOTATIONS_PATH:-./var/runtime/annotations}:/app/annotations:ro
      - ${TRAINED_MODELS_PATH:-./var/runtime/trained_models}:/app/var/trained_models:ro
      # Backtest artifacts (writable cho CI runs)
      - ${BACKTEST_PATH:-./var/runtime/backtest}:/app/var/backtest
      # HF model cache (named volume, bind-backed)
      - hf_cache:/models/huggingface
      # Logs (writable)
      - ${LOGS_PATH:-./logs}/app:/app/logs
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    networks:
      - frontend
      - backend

  # =========================================================================
  # Nginx reverse proxy
  # =========================================================================
  nginx:
    image: nginx:1.27-alpine
    container_name: brightify_nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./nginx/certs:/etc/letsencrypt:ro
      - ./nginx/www:/var/www/certbot:ro
      - ./static:/var/www/static:ro
    depends_on:
      app:
        condition: service_healthy
    networks:
      - frontend

volumes:
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${DB_DATA_PATH:-./var/volumes/postgres_data}
  redis_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${REDIS_DATA_PATH:-./var/volumes/redis_data}
  hf_cache:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${HF_CACHE_PATH:-./var/volumes/hf_cache}

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true   # No internet egress
```

> **Quan trọng**: named volumes dùng `driver_opts: type=none, o=bind, device=...` để thực chất là bind mount → portable, backup được như folder thường, nhưng Docker vẫn quản lý lifecycle. Đây là kỹ thuật **bind-backed named volume**, kết hợp ưu điểm cả 2 cách mount.

> Trước khi `docker compose up`, phải `mkdir -p var/volumes/{postgres_data,redis_data,hf_cache}` (script `make init` sẽ tự làm).

### 6.2 Dev override `docker-compose.dev.yml`

```yaml
services:
  db:
    ports:
      - "5432:5432"   # Expose for local dbeaver/pgadmin
    command:
      - postgres
      - -c
      - log_statement=all   # debug
      - -c
      - shared_buffers=1GB

  app:
    build:
      target: runtime
    command: >
      uvicorn app:app
      --host 0.0.0.0
      --port 8000
      --reload                  # hot reload
      --reload-dir /app
      --log-level debug
    environment:
      DEBUG: "true"
      LOG_LEVEL: DEBUG
    volumes:
      # Bind mount code cho hot reload
      - .:/app
      # Override read-only mounts với read-write trong dev
      - ./music_files:/app/music_files
      - ./album_art:/app/album_art
    ports:
      - "8000:8000"   # Direct access without nginx

  nginx:
    profiles: ["donotstart"]   # Disable nginx trong dev
```

Chạy dev:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### 6.3 Prod override `docker-compose.prod.yml`

```yaml
services:
  db:
    secrets:
      - db_password
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'
        reservations:
          memory: 2G
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"

  app:
    secrets:
      - admin_key
    environment:
      BRIGHTIFY_ADMIN_KEY_FILE: /run/secrets/admin_key
      LOG_LEVEL: INFO
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 4G
          cpus: '2.0'
        reservations:
          memory: 2G
          cpus: '1.0'
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"

secrets:
  db_password:
    file: ./secrets/db_password.txt
  admin_key:
    file: ./secrets/admin_key.txt
```

Chạy prod:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 7. DATA LAYOUT & PERSISTENCE (MASTER GUIDE)

> **Master guide cho mọi data trong Brightify** — đây là **single source of truth**. Các Plan 1, 2 và mọi tài liệu khác đều phải tuân theo layout này.

### 7.1 Triết lý 4 tiers

Mọi artifact của Brightify thuộc 1 trong 4 tiers:

| Tier | Tên | Vị trí | Lifecycle | Backup | Ví dụ |
|---|---|---|---|---|---|
| **T1** | Code | Git repository | Permanent (git history) | Git distributed | `.py`, `.md`, `requirements.txt`, init scripts |
| **T2** | Runtime data | Host filesystem (bind mount) | Persistent, project-scoped | rsync + weekly snapshot | MP3, art, processed CSV/NPY, lyrics |
| **T3** | Docker volumes | Managed named volumes | Persistent (cho DB) hoặc ephemeral (cho cache) | DB: pg_dump daily; cache: re-downloadable | PostgreSQL data, HF cache, Redis |
| **T4** | Backup | Off-site (S3/R2/Backblaze) | Archival, versioned | 30-day retention | DB dumps, T2 snapshots |

**Nguyên tắc:** Mỗi artifact phải đặt đúng tier. Nếu mơ hồ → mặc định T2 (bind mount, an toàn nhất).

### 7.2 Canonical directory layout

```
${BRIGHTIFY_ROOT}/                 ← /opt/brightify ở prod, repo root ở dev
│
├── app/                           ← T1: code (git clone từ repo)
│   ├── api/, core/, db/, tools/, static/
│   ├── Dockerfile
│   ├── docker-compose.yml + overrides
│   └── ...
│
└── var/                           ← T2 + T3 mounts (KHÔNG trong git)
    │
    ├── runtime/                   ← T2: bind mounts (large, project-owned data)
    │   ├── music_files/           # 10-50 GB — MP3 từ pipeline phase 3
    │   ├── album_art/             # 1-2 GB — album JPGs
    │   ├── artist_images/         # 200-500 MB — artist JPGs
    │   ├── checkpoints/           # 100-500 MB — pipeline output (resumable)
    │   ├── processed/             # ~200 MB — CSV + NPY embeddings
    │   │   ├── vietnamese_music_processed_full.csv
    │   │   ├── vietnamese_music_embeddings_full.npy
    │   │   ├── mert_embeddings.npy           # Plan 1, Pillar A
    │   │   ├── clap_embeddings.npy           # Plan 1, Pillar A (optional)
    │   │   ├── kg_song_embeddings.npy        # Plan 1, Pillar F
    │   │   └── embeddings_metadata.json
    │   ├── essentia_models/       # ~150 MB — .pb files (binary, version pinned)
    │   ├── annotations/           # < 10 MB — Vietnamese mood labels
    │   │   ├── vn_mood_500.csv               # Plan 1, Pillar E
    │   │   └── annotators_metadata.json
    │   ├── backtest/              # 50-200 MB — test artifacts & reports
    │   │   ├── ground_truth/                 # Plan 2
    │   │   │   ├── mood_based_v1.json
    │   │   │   ├── playlist_editorial_v1.json
    │   │   │   └── synthetic_users_v1.json
    │   │   ├── baselines/                    # Plan 2
    │   │   │   └── v7.2_metrics.json
    │   │   └── reports/                      # Plan 2 — versioned by date
    │   │       └── 2026-05-26_full/
    │   │           ├── report.md
    │   │           ├── report.json
    │   │           └── dashboard.html
    │   └── trained_models/        # Plan 1 outputs
    │       ├── emotion_combiner_v1.onnx      # Plan 1, Pillar E
    │       └── reranker_finetuned_v1/        # Plan 1, Pillar C (optional)
    │
    ├── volumes/                   ← T3: Docker named volumes (Docker managed)
    │   ├── postgres_data/         # Mapped from named volume `postgres_data`
    │   ├── redis_data/            # Mapped from named volume `redis_data`
    │   └── hf_cache/              # HF auto-download cache (re-downloadable)
    │
    ├── secrets/                   ← T2: secrets files (chmod 600)
    │   ├── db_password.txt
    │   ├── admin_key.txt
    │   └── redis_password.txt
    │
    ├── backups/                   ← T2 → T4: local DB dumps trước khi sync off-site
    │   ├── db/
    │   │   └── brightify_YYYYMMDD_HHMMSS.sql.gz
    │   └── snapshots/
    │       └── runtime_YYYYMMDD.tar.zst
    │
    └── logs/                      ← T2: app + nginx logs (rotated)
        ├── app/
        ├── nginx/
        └── postgres/
```

### 7.3 Bind mount path resolution (env-driven)

Để cùng compose file hoạt động cả dev (repo-local) lẫn prod (external `/var`):

```yaml
# docker-compose.yml
services:
  app:
    volumes:
      - ${MUSIC_FILES_PATH:-./music_files}:/app/music_files:ro
      - ${ALBUM_ART_PATH:-./album_art}:/app/album_art:ro
      - ${ARTIST_IMAGES_PATH:-./artist_images}:/app/artist_images:ro
      - ${CHECKPOINTS_PATH:-./checkpoints}:/app/checkpoints:ro
      - ${PROCESSED_PATH:-./data}:/app/data:ro
      - ${ESSENTIA_MODELS_PATH:-./models_cache}:/app/models_cache:ro
      - ${ANNOTATIONS_PATH:-./var/runtime/annotations}:/app/annotations:ro
      - ${BACKTEST_PATH:-./var/runtime/backtest}:/app/var/backtest
      - ${TRAINED_MODELS_PATH:-./var/runtime/trained_models}:/app/var/trained_models
      - ${LOGS_PATH:-./logs}:/app/logs

  db:
    volumes:
      - postgres_data:/var/lib/postgresql/data
      # Override possible:
      # - ${DB_DATA_PATH:-postgres_data}:/var/lib/postgresql/data

volumes:
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${DB_DATA_PATH:-./var/volumes/postgres_data}
  redis_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${REDIS_DATA_PATH:-./var/volumes/redis_data}
  hf_cache:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${HF_CACHE_PATH:-./var/volumes/hf_cache}
```

**Mẹo:** Dùng `driver_opts: type=none, o=bind, device=path` để named volumes thực ra là bind mount → portable, backup được như folder thường, nhưng vẫn quản lý qua Docker.

### 7.4 Environment variables cho data paths

```bash
# .env.dev (repo-local)
BRIGHTIFY_ROOT=.
MUSIC_FILES_PATH=./music_files
ALBUM_ART_PATH=./album_art
ARTIST_IMAGES_PATH=./artist_images
CHECKPOINTS_PATH=./checkpoints
PROCESSED_PATH=./data
ESSENTIA_MODELS_PATH=./models_cache
ANNOTATIONS_PATH=./var/runtime/annotations
BACKTEST_PATH=./var/runtime/backtest
TRAINED_MODELS_PATH=./var/runtime/trained_models
DB_DATA_PATH=./var/volumes/postgres_data
REDIS_DATA_PATH=./var/volumes/redis_data
HF_CACHE_PATH=./var/volumes/hf_cache
LOGS_PATH=./logs
BACKUPS_PATH=./var/backups
```

```bash
# .env.prod (external var/)
BRIGHTIFY_ROOT=/opt/brightify
MUSIC_FILES_PATH=/opt/brightify/var/runtime/music_files
ALBUM_ART_PATH=/opt/brightify/var/runtime/album_art
ARTIST_IMAGES_PATH=/opt/brightify/var/runtime/artist_images
CHECKPOINTS_PATH=/opt/brightify/var/runtime/checkpoints
PROCESSED_PATH=/opt/brightify/var/runtime/processed
ESSENTIA_MODELS_PATH=/opt/brightify/var/runtime/essentia_models
ANNOTATIONS_PATH=/opt/brightify/var/runtime/annotations
BACKTEST_PATH=/opt/brightify/var/runtime/backtest
TRAINED_MODELS_PATH=/opt/brightify/var/runtime/trained_models
DB_DATA_PATH=/opt/brightify/var/volumes/postgres_data
REDIS_DATA_PATH=/opt/brightify/var/volumes/redis_data
HF_CACHE_PATH=/opt/brightify/var/volumes/hf_cache
LOGS_PATH=/opt/brightify/var/logs
BACKUPS_PATH=/opt/brightify/var/backups
```

→ **Cùng compose, khác env file** → dev và prod identical behavior, chỉ khác path.

### 7.5 Strategy decision matrix

| Artifact | Size | Update freq | Tier | Mount type | Reasoning |
|---|---|---|---|---|---|
| `music_files/` MP3 | 10-50 GB | Khi pipeline chạy | T2 | Bind `:ro` | Quá lớn cho image; cần rsync mgmt; ro để app không sửa |
| `album_art/`, `artist_images/` | 1-2 GB | Khi pipeline | T2 | Bind `:ro` | Tương tự MP3 |
| `checkpoints/` | 100-500 MB | Mỗi lần chạy pipeline | T2 | Bind `:ro` | App đọc; pipeline (CLI) ghi qua bind RW khi cần |
| `processed/*.csv` | ~50 MB | Khi pipeline phase 6 | T2 | Bind `:ro` | App load vào RAM lúc startup; dùng symlink để versioning |
| `processed/*.npy` (PhoBERT) | ~13 MB | Khi pipeline phase 6 | T2 | Bind `:ro` | Đọc 1 lần lúc startup |
| `processed/mert_embeddings.npy` | ~13 MB | Plan 1 Pillar A | T2 | Bind `:ro` | Tương tự PhoBERT |
| `processed/kg_embeddings.npy` | ~1 MB | Plan 1 Pillar F | T2 | Bind `:ro` | Tương tự |
| `essentia_models/*.pb` | ~150 MB | Khi upgrade model | T2 | Bind `:ro` | Pinning version trong git LFS hoặc release artifact |
| `annotations/vn_mood_500.csv` | < 1 MB | Khi annotation hoàn thành | T2 | Bind `:ro` | Plan 1 Pillar E + Plan 2 ground truth |
| `backtest/ground_truth/` | < 100 MB | Khi rebuild test set | T2 | Bind `:ro` | Plan 2 — versioned by `_v1, v2...` |
| `backtest/reports/` | < 200 MB tổng | Mỗi CI run | T2 | Bind RW | Plan 2 — writable từ CI/Cron |
| `trained_models/*.onnx` | ~50 MB | Khi retrain | T2 | Bind `:ro` | Plan 1 Pillar E combiner |
| HF model cache | 2-3 GB | Re-downloadable | T3 | Named volume (bind-backed) | Nếu xóa → auto re-download ~10 phút |
| PostgreSQL data | 1-5 GB | Mọi write | T3 | Named volume (bind-backed) | Performance + pg_dump backup |
| Redis data | < 100 MB | Mọi write | T3 | Named volume | Cache, có thể mất |
| Backups | varies | Cron daily | T2 → T4 | Bind RW + rclone | Local 7-30 days, off-site 30+ days |

### 7.6 Tại sao bind mount cho MP3 và assets lớn

- **Performance**: Linux native bind ≈ named volume.
- **Management**: rsync, tar, cp như filesystem thường.
- **Update workflow**: thêm MP3 mới không cần restart container.
- **Backup**: tar/zstd 1-pass, không phụ thuộc Docker.
- **Migration**: copy folder sang server khác = xong.

> Trên macOS/Windows (dev), bind mount qua VM chậm với nhiều file nhỏ. Trong dev có thể fallback named volume + đồng bộ qua `docker cp` hoặc Mutagen. **Production luôn Linux native.**

### 7.7 HF model cache strategy

```yaml
volumes:
  hf_cache:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${HF_CACHE_PATH}   # bind-backed named volume
```

**First-time warmup (CI hoặc setup script):**

```bash
docker compose run --rm app python -c "
from transformers import AutoTokenizer, AutoModel, CLIPModel, CLIPProcessor
AutoTokenizer.from_pretrained('vinai/phobert-base-v2')
AutoModel.from_pretrained('vinai/phobert-base-v2')
CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')
CLIPModel.from_pretrained('openai/clip-vit-base-patch32')

# Sau Pillar A:
# AutoModel.from_pretrained('m-a-p/MERT-v1-95M', trust_remote_code=True)
# (CLAP optional)
"
```

Sau khi warm, set `HF_HUB_OFFLINE=1` ở production để chặn re-download bất ngờ.

### 7.8 Essentia models — bind mount T2

**Thay đổi so với phiên bản trước plan: KHÔNG copy vào image** (sẽ làm image phồng + khó update).

Thay vào đó:
- Bind mount `./models_cache` (dev) hoặc `/opt/brightify/var/runtime/essentia_models` (prod) → `/app/models_cache:ro`.
- Models tracked qua **git LFS** hoặc download script (`scripts/download-essentia-models.sh`).
- Khi upgrade model: drop file mới vào folder, không cần rebuild image.

```bash
# scripts/download-essentia-models.sh
mkdir -p models_cache
cd models_cache
# DEAM
wget -O deam-msd-musicnn-2.pb https://essentia.upf.edu/models/.../deam-msd-musicnn-2.pb
# EffNet-Discogs
wget -O discogs_effnet-bs64-1.pb ...
# Tempo
wget -O deepsquare-k16-3.pb ...
# Timbre
wget -O timbre-discogs-effnet-1.pb ...
```

### 7.9 Snapshot lock (versioning artifacts)

Để rollback dễ, đặt **symlink** trong `processed/` và `trained_models/`:

```
processed/
├── current → 2026-05-26/        # symlink trỏ phiên bản đang dùng
├── 2026-05-26/
│   ├── vietnamese_music_processed_full.csv
│   ├── vietnamese_music_embeddings_full.npy
│   └── mert_embeddings.npy
└── 2026-04-15/                  # version cũ, giữ lại để rollback
    └── ...
```

App đọc `processed/current/...` → đổi symlink = rollback instantly.

```bash
# Rollback
cd var/runtime/processed
rm current
ln -s 2026-04-15 current
docker compose restart app
```

---

## 8. SECRETS & CẤU HÌNH

### 8.1 Environment variables (full list)

```bash
# .env.example
# ===== Database =====
POSTGRES_USER=brightify
POSTGRES_PASSWORD=changeme_in_prod
POSTGRES_DB=brightify

# ===== App =====
DATABASE_URL=postgresql+asyncpg://brightify:changeme_in_prod@db:5432/brightify
REDIS_URL=redis://redis:6379/0
ALLOWED_ORIGINS=http://localhost,https://brightify.example.com
BRIGHTIFY_ADMIN_KEY=generate_with_openssl_rand_hex_32
LOG_LEVEL=INFO

# ===== Optional =====
HF_HUB_OFFLINE=0    # Set to 1 in production after warmup
SENTRY_DSN=         # Optional
```

### 8.2 Dev: `.env` file

- Local dev: dùng `.env` file (gitignored).
- Compose auto-loads `.env` ở project root.

### 8.3 Prod: Docker secrets

```bash
# Generate secrets
mkdir -p secrets
openssl rand -hex 32 > secrets/db_password.txt
openssl rand -hex 32 > secrets/admin_key.txt
chmod 600 secrets/*.txt
```

App phải đọc từ file:

```python
# config.py
def _read_secret_or_env(name: str, default: str = "") -> str:
    file_var = f"{name}_FILE"
    if file_path := os.environ.get(file_var):
        with open(file_path) as f:
            return f.read().strip()
    return os.environ.get(name, default)

BRIGHTIFY_ADMIN_KEY = _read_secret_or_env("BRIGHTIFY_ADMIN_KEY")
```

### 8.4 Secrets management nâng cao (cloud)

Production-grade:
- AWS Secrets Manager + IAM role
- HashiCorp Vault
- Doppler / Infisical (SaaS)

→ Out of scope cho MVP nhưng nên consider khi scale.

---

## 9. NGINX REVERSE PROXY & SSL

### 9.1 `nginx/nginx.conf`

```nginx
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time uct="$upstream_connect_time" '
                    'urt="$upstream_response_time"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    server_tokens off;

    # Gzip
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript
               application/json application/javascript application/xml+rss
               application/atom+xml image/svg+xml;

    # Rate limiting zones
    limit_req_zone $binary_remote_addr zone=api_general:10m rate=60r/m;
    limit_req_zone $binary_remote_addr zone=api_recommend:10m rate=30r/m;

    # Upload size
    client_max_body_size 12M;   # cho image upload

    include /etc/nginx/conf.d/*.conf;
}
```

### 9.2 `nginx/conf.d/brightify.conf`

```nginx
# HTTP → HTTPS redirect
server {
    listen 80;
    server_name brightify.example.com;

    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # All other → HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name brightify.example.com;

    ssl_certificate /etc/letsencrypt/live/brightify.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/brightify.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Static frontend
    location / {
        root /var/www/static;
        try_files $uri $uri/ /index.html;
        expires 1h;
    }

    # API → app
    location /api/ {
        limit_req zone=api_general burst=20 nodelay;

        proxy_pass http://app:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 60s;
        proxy_connect_timeout 30s;
    }

    # Recommendation endpoints (stricter rate limit)
    location ~ ^/api/(recommend|backtest)/ {
        limit_req zone=api_recommend burst=10 nodelay;

        proxy_pass http://app:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 120s;   # ML inference cần thời gian
    }

    # Audio streaming
    location /api/audio/stream/ {
        proxy_pass http://app:8000;
        proxy_buffering off;
        proxy_set_header Range $http_range;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Album art / artist image (cached aggressively)
    location ~ ^/api/(album-art|artist-image)/ {
        proxy_pass http://app:8000;
        proxy_cache_valid 200 24h;
        add_header X-Cache-Status $upstream_cache_status;
    }
}
```

### 9.3 Let's Encrypt với certbot

```yaml
# docker-compose.prod.yml thêm
services:
  certbot:
    image: certbot/certbot:latest
    container_name: brightify_certbot
    volumes:
      - ./nginx/certs:/etc/letsencrypt
      - ./nginx/www:/var/www/certbot
    entrypoint: >
      sh -c "trap exit TERM; while :; do
        certbot renew --webroot -w /var/www/certbot --quiet;
        sleep 12h & wait $${!};
      done"
    networks:
      - frontend
```

Initial cert (chạy 1 lần):
```bash
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  --email admin@example.com \
  --agree-tos --no-eff-email \
  -d brightify.example.com
```

---

## 10. MIGRATION & SEED FLOW

### 10.1 Migration container (one-shot)

```yaml
migrate:
  <<: *app-base
  command: alembic upgrade head
  depends_on:
    db:
      condition: service_healthy
  restart: "no"   # Một lần là đủ
```

App `depends_on: migrate: condition: service_completed_successfully` → app chỉ khởi động sau khi migration thành công.

### 10.2 Seed flow (lần đầu)

```bash
# 1. Khởi động db
docker compose up -d db

# 2. Đợi db healthy
docker compose ps  # check "healthy"

# 3. Chạy migration
docker compose run --rm migrate

# 4. Seed từ CSV
docker compose run --rm app python -m db.seed

# 5. Khởi động full stack
docker compose up -d
```

### 10.3 Seed automation script

```bash
# scripts/initial-setup.sh
#!/bin/bash
set -euo pipefail

echo "🚀 Brightify initial setup"

# 1. Generate secrets nếu chưa có
if [ ! -f secrets/db_password.txt ]; then
  mkdir -p secrets
  openssl rand -hex 32 > secrets/db_password.txt
  openssl rand -hex 32 > secrets/admin_key.txt
  chmod 600 secrets/*.txt
  echo "✓ Generated secrets"
fi

# 2. Start db
docker compose up -d db redis
echo "⏳ Waiting for db..."
until docker compose exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
  sleep 2
done
echo "✓ DB ready"

# 3. Run migration
docker compose run --rm migrate
echo "✓ Migrations applied"

# 4. Check if seeded
SONG_COUNT=$(docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT COUNT(*) FROM songs;" 2>/dev/null || echo "0")

if [ "$SONG_COUNT" -lt "100" ]; then
  echo "📦 Seeding database (this may take 5-10 minutes)..."
  docker compose run --rm app python -m db.seed
  echo "✓ Database seeded"
else
  echo "✓ Database already has $SONG_COUNT songs, skipping seed"
fi

# 5. Warmup model cache
echo "🤖 Warming up model cache..."
docker compose run --rm app python -c "
from transformers import AutoTokenizer, AutoModel, CLIPModel, CLIPProcessor
AutoTokenizer.from_pretrained('vinai/phobert-base-v2')
AutoModel.from_pretrained('vinai/phobert-base-v2')
CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')
CLIPModel.from_pretrained('openai/clip-vit-base-patch32')
print('✓ Models cached')
"

# 6. Start full stack
docker compose up -d
echo "🎉 Brightify is ready at http://localhost"
```

### 10.4 Update workflow

```bash
# Pull latest code
git pull

# Rebuild với layer cache
docker compose build app

# Apply new migrations
docker compose run --rm migrate

# Rolling restart
docker compose up -d --no-deps --build app

# Verify
curl -fsS http://localhost/api/health
```

---

## 11. PRODUCTION HARDENING

### 11.1 Resource limits

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'
        reservations:
          memory: 2G

  db:
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'

  redis:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
```

### 11.2 Non-root user (đã có trong Dockerfile)

Verify trong container:
```bash
docker compose exec app whoami   # Phải là "app", không phải "root"
docker compose exec app id       # uid=1000(app) gid=1000(app)
```

### 11.3 Read-only root filesystem (advanced)

```yaml
services:
  app:
    read_only: true
    tmpfs:
      - /tmp:size=512M
      - /app/logs:size=128M
```

Sau đó verify mọi write đều vào `/tmp`, `/app/logs`, hoặc các named volume mount.

### 11.4 Security scanning

```bash
# Trivy scan
docker run --rm aquasec/trivy:latest image brightify:latest

# Docker Bench
docker run --rm --net host --pid host --userns host --cap-add audit_control \
  -v /var/lib:/var/lib -v /var/run/docker.sock:/var/run/docker.sock \
  docker/docker-bench-security
```

### 11.5 Network policies

- `backend` network `internal: true` → DB, Redis không có internet egress.
- `frontend` network → chỉ nginx + app expose ra ngoài.
- Không expose DB ports trong prod compose file.

### 11.6 Backup & disaster recovery

- DB backup cron (xem 5.6).
- Model cache backup (rare, before major upgrade).
- Configuration in git (mọi config phải tracked).

### 11.7 Update strategy

- **Rolling update** với `docker compose up -d --no-deps --build app`.
- **Blue-green** (advanced): 2 app instances, nginx upstream switch.
- **Rollback**: keep last 3 images tagged với version.

### 11.8 Backup & restore comprehensive

#### 11.8.1 Backup matrix (cái gì, bao lâu, đâu)

| Asset | Frequency | Retention | Local | Off-site (S3/R2) | Tool |
|---|---|---|---|---|---|
| **PostgreSQL** | Daily 03:00 | 7 days local, 30 days off-site | `var/backups/db/` | `s3://brightify-backup/db/` | `pg_dump` + `rclone` |
| **processed/** (CSV+NPY) | Weekly Sunday | 4 weeks local, 12 weeks off-site | `var/backups/snapshots/` | `s3://brightify-backup/snapshots/` | `tar zstd` + `rclone` |
| **annotations/** | Khi update | All versions | git LFS (small) | git remote | git |
| **trained_models/** | Khi train xong | Last 3 versions | `var/backups/models/` | `s3://brightify-backup/models/` | `tar` + `rclone` |
| **backtest reports** | Permanent | All | `var/runtime/backtest/reports/` | `s3://brightify-backup/backtest/` | rsync |
| **music_files/** | Quarterly | 1 archive | External HDD | `s3://brightify-backup/music/` (Glacier) | `tar zstd` |
| **album_art/, artist_images/** | Cùng với music | 1 archive | External HDD | Glacier | `tar zstd` |
| **Configs + secrets** | Khi thay đổi | All | git encrypted (SOPS) | git remote | `git-crypt` hoặc SOPS |

#### 11.8.2 Backup scripts

```bash
# scripts/backup-db.sh — daily cron 03:00
#!/bin/bash
set -euo pipefail

BACKUPS_PATH="${BACKUPS_PATH:-./var/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_DIR="$BACKUPS_PATH/db"
FILENAME="brightify_${TIMESTAMP}.sql.gz"

mkdir -p "$DB_DIR"

# Dump
docker compose exec -T db pg_dump \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  --no-owner --clean --if-exists --serializable-deferrable \
  | gzip -9 > "$DB_DIR/$FILENAME"

# Verify
gunzip -t "$DB_DIR/$FILENAME" || { echo "❌ Backup corrupt"; exit 1; }
SIZE=$(stat -f%z "$DB_DIR/$FILENAME" 2>/dev/null || stat -c%s "$DB_DIR/$FILENAME")
echo "✓ DB dump: $FILENAME ($(numfmt --to=iec <<< $SIZE))"

# Rotate local (keep 7 days)
find "$DB_DIR" -name "brightify_*.sql.gz" -mtime +7 -delete

# Off-site sync (rclone configured separately)
if command -v rclone >/dev/null; then
  rclone copy "$DB_DIR/$FILENAME" "brightify-backup:db/" --quiet
fi
```

```bash
# scripts/backup-snapshot.sh — weekly cron Sunday 04:00
#!/bin/bash
set -euo pipefail

BACKUPS_PATH="${BACKUPS_PATH:-./var/backups}"
RUNTIME_PATH="${RUNTIME_PATH:-./var/runtime}"
TIMESTAMP=$(date +%Y%m%d)
SNAP_DIR="$BACKUPS_PATH/snapshots"
FILENAME="runtime_${TIMESTAMP}.tar.zst"

mkdir -p "$SNAP_DIR"

# Snapshot processed + annotations + trained_models + backtest/ground_truth
tar --use-compress-program='zstd -19 -T0' \
    -cf "$SNAP_DIR/$FILENAME" \
    -C "$RUNTIME_PATH" \
    processed annotations trained_models backtest/ground_truth backtest/baselines

echo "✓ Snapshot: $FILENAME"

# Rotate local (4 weeks)
find "$SNAP_DIR" -name "runtime_*.tar.zst" -mtime +28 -delete

# Off-site
if command -v rclone >/dev/null; then
  rclone copy "$SNAP_DIR/$FILENAME" "brightify-backup:snapshots/" --quiet
fi
```

```bash
# scripts/backup-music.sh — quarterly, manual or cron
#!/bin/bash
# Backup MP3 archive (very large, infrequent)
TIMESTAMP=$(date +%Y%m%d)
tar --use-compress-program='zstd -3 -T0' \
    -cf "/mnt/external-hdd/music_${TIMESTAMP}.tar.zst" \
    "${MUSIC_FILES_PATH}"
```

#### 11.8.3 Restore runbook

**Scenario 1: DB corruption / accidental drop**

```bash
# 1. Stop app
docker compose stop app

# 2. Find latest good dump
ls -lh var/backups/db/

# 3. Restore (drops existing tables, recreates)
gunzip -c var/backups/db/brightify_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

# 4. Verify
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT COUNT(*) FROM songs;"

# 5. Restart app
docker compose start app
```

**Scenario 2: Migrate to new server**

```bash
# Trên server cũ
bash scripts/backup-db.sh
bash scripts/backup-snapshot.sh
rsync -avP var/runtime/music_files/ user@newserver:/opt/brightify/var/runtime/music_files/
rsync -avP var/runtime/album_art/ var/runtime/artist_images/ user@newserver:/opt/brightify/var/runtime/

# Trên server mới
cd /opt/brightify
git clone <repo> app && cd app
cp .env.prod .env
docker compose up -d db redis
sleep 15
gunzip -c /path/to/brightify_*.sql.gz | docker compose exec -T db psql -U $POSTGRES_USER -d $POSTGRES_DB
tar -I 'zstd -d' -xf /path/to/runtime_*.tar.zst -C /opt/brightify/var/runtime/
docker compose run --rm migrate    # apply any new migrations
docker compose up -d
```

**Scenario 3: Rollback artifact (processed CSV / embeddings)**

```bash
# Bằng symlink (xem 7.9)
cd var/runtime/processed
rm current
ln -s 2026-04-15 current
docker compose restart app
```

**Scenario 4: Disaster recovery (server bị xóa hoàn toàn)**

```bash
# Trên server mới
git clone <repo> app && cd app

# Pull backups từ off-site
rclone copy brightify-backup:db/$(rclone lsf brightify-backup:db/ | tail -1) /tmp/
rclone copy brightify-backup:snapshots/$(rclone lsf brightify-backup:snapshots/ | tail -1) /tmp/

# Restore
docker compose up -d db
sleep 15
docker compose run --rm migrate
gunzip -c /tmp/brightify_*.sql.gz | docker compose exec -T db psql ...
tar -I 'zstd -d' -xf /tmp/runtime_*.tar.zst -C /opt/brightify/var/runtime/

# music_files cần restore từ Glacier (chậm hơn)
rclone copy brightify-backup-glacier:music/latest.tar.zst /tmp/
tar -I 'zstd -d' -xf /tmp/latest.tar.zst -C /opt/brightify/var/runtime/

docker compose up -d
```

#### 11.8.4 Backup verification (drill schedule)

| Cadence | Action | Goal |
|---|---|---|
| **Weekly** | Restore latest DB dump vào staging | Verify dump integrity |
| **Monthly** | Full DR drill (new VM, full restore) | Verify runbook hoạt động |
| **Quarterly** | Restore music archive từ Glacier | Verify cold storage |

#### 11.8.5 Cron crontab mẫu

```cron
# /etc/cron.d/brightify
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
BRIGHTIFY_ROOT=/opt/brightify
SHELL=/bin/bash

# Daily DB dump
0 3 * * * brightify cd $BRIGHTIFY_ROOT/app && bash scripts/backup-db.sh >> $BRIGHTIFY_ROOT/var/logs/backup-db.log 2>&1

# Weekly runtime snapshot (Sunday 04:00)
0 4 * * 0 brightify cd $BRIGHTIFY_ROOT/app && bash scripts/backup-snapshot.sh >> $BRIGHTIFY_ROOT/var/logs/backup-snapshot.log 2>&1

# Weekly restore drill (Monday 05:00) — restore vào staging DB
0 5 * * 1 brightify cd $BRIGHTIFY_ROOT/app && bash scripts/restore-drill.sh >> $BRIGHTIFY_ROOT/var/logs/restore-drill.log 2>&1

# Quarterly music archive (1st of Jan/Apr/Jul/Oct, 06:00)
0 6 1 1,4,7,10 * brightify cd $BRIGHTIFY_ROOT/app && bash scripts/backup-music.sh >> $BRIGHTIFY_ROOT/var/logs/backup-music.log 2>&1
```

---

## 12. MULTI-ENVIRONMENT (DEV/STAGING/PROD)

### 12.1 Compose profiles strategy

```bash
# Dev: base + dev override
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Staging: base + staging override
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d

# Prod: base + prod override
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 12.2 Differences matrix

| Aspect | Dev | Staging | Prod |
|---|---|---|---|
| Code mount | Bind (hot reload) | Image only | Image only |
| Logging | DEBUG | INFO | INFO |
| Nginx | Disabled | Enabled | Enabled |
| SSL | Self-signed | Let's Encrypt staging | Let's Encrypt prod |
| Secrets | `.env` | Docker secrets | Docker secrets / Vault |
| DB ports exposed | Yes (5432) | No | No |
| Replicas | 1 | 1 | 2+ |
| Resource limits | None | Reduced | Full |
| Backup | No | Daily | Daily + offsite |
| Monitoring | Console | Prometheus | Prometheus + Grafana + Alert |

### 12.3 Convenience Makefile

```makefile
# Makefile
.PHONY: init dev staging prod migrate seed shell logs clean backup restore

init:           ## Tạo var/ structure + secrets cho lần đầu setup
	@mkdir -p var/runtime/{music_files,album_art,artist_images,checkpoints,processed,essentia_models,annotations,trained_models}
	@mkdir -p var/runtime/backtest/{ground_truth,test_sets,baselines,reports,ci_artifacts}
	@mkdir -p var/volumes/{postgres_data,redis_data,hf_cache}
	@mkdir -p var/secrets var/backups/{db,snapshots,models} var/logs/{app,nginx,postgres}
	@chmod 700 var/secrets
	@if [ ! -f var/secrets/db_password.txt ]; then \
		openssl rand -hex 32 > var/secrets/db_password.txt; \
		openssl rand -hex 32 > var/secrets/admin_key.txt; \
		openssl rand -hex 32 > var/secrets/redis_password.txt; \
		chmod 600 var/secrets/*.txt; \
		echo "✓ Generated secrets"; \
	fi
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✓ Created .env from .env.example — review and customize!"; \
	fi
	@echo "✓ Brightify directory structure ready"

dev: init       ## Start dev stack với hot reload
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

dev-detach: init
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

staging: init
	docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d

prod: init
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

migrate:        ## Apply Alembic migrations
	docker compose run --rm migrate

seed:           ## Seed DB từ processed CSV
	docker compose run --rm app python -m db.seed

warmup:         ## Pre-download HF models vào hf_cache volume
	docker compose run --rm app python -c "\
from transformers import AutoTokenizer, AutoModel, CLIPModel, CLIPProcessor; \
AutoTokenizer.from_pretrained('vinai/phobert-base-v2'); \
AutoModel.from_pretrained('vinai/phobert-base-v2'); \
CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32'); \
CLIPModel.from_pretrained('openai/clip-vit-base-patch32'); \
print('✓ Models cached')"

shell:          ## Open shell vào app container
	docker compose exec app /bin/bash

dbshell:        ## Open psql shell
	docker compose exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

logs:           ## Tail tất cả logs
	docker compose logs -f --tail=100

logs-app:
	docker compose logs -f app

backup:         ## Manual DB backup ngay lập tức
	bash scripts/backup-db.sh

backup-snapshot:## Manual runtime snapshot
	bash scripts/backup-snapshot.sh

restore-db:     ## Restore latest DB dump (PROMPT confirmation)
	@echo "⚠ This will REPLACE current DB. Latest backup:"
	@ls -t var/backups/db/*.sql.gz | head -1
	@read -p "Continue? (yes/no) " ANS && [ "$$ANS" = "yes" ] || exit 1
	gunzip -c $$(ls -t var/backups/db/*.sql.gz | head -1) | \
		docker compose exec -T db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

clean:          ## Stop + remove containers (KEEPS volumes)
	docker compose down
	@echo "✓ Containers down. Volumes preserved in var/volumes/"

clean-all:      ## ⚠ DANGER: xóa tất cả (containers + named volumes)
	@echo "⚠⚠⚠ This will DELETE postgres_data + redis_data + hf_cache!"
	@read -p "Type 'DELETE' to confirm: " ANS && [ "$$ANS" = "DELETE" ] || exit 1
	docker compose down -v
	rm -rf var/volumes/* var/logs/*

reset-db: backup ## Backup hiện tại + reset DB từ seed
	docker compose stop app db
	rm -rf var/volumes/postgres_data/*
	docker compose up -d db
	@sleep 10
	$(MAKE) migrate seed
	docker compose start app

verify:         ## Health check tất cả services
	@docker compose ps
	@curl -fsS http://localhost:8000/api/health | python -m json.tool || echo "❌ App unhealthy"
```

> **Mọi target đều safe**: `clean` chỉ stop containers, giữ data. Phải explicit `clean-all` mới xóa volumes (yêu cầu type "DELETE" để xác nhận).

---

## 13. CI/CD PIPELINE

### 13.1 GitHub Actions: Build + Test

```yaml
# .github/workflows/docker-build.yml
name: Docker Build & Test

on:
  push:
    branches: [main, develop]
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Cache Docker layers
        uses: actions/cache@v4
        with:
          path: /tmp/.buildx-cache
          key: ${{ runner.os }}-buildx-${{ github.sha }}
          restore-keys: |
            ${{ runner.os }}-buildx-

      - name: Build app image
        uses: docker/build-push-action@v5
        with:
          context: .
          load: true
          tags: brightify:test
          cache-from: type=local,src=/tmp/.buildx-cache
          cache-to: type=local,dest=/tmp/.buildx-cache-new,mode=max

      - name: Image size check
        run: |
          SIZE=$(docker image inspect brightify:test --format='{{.Size}}')
          MAX_SIZE=3221225472   # 3 GB
          if [ "$SIZE" -gt "$MAX_SIZE" ]; then
            echo "❌ Image too large: $SIZE bytes > $MAX_SIZE"
            exit 1
          fi
          echo "✓ Image size: $(echo $SIZE | numfmt --to=iec)"

      - name: Start stack
        run: |
          cp .env.example .env
          docker compose up -d db redis
          sleep 15
          docker compose run --rm migrate

      - name: Smoke test
        run: |
          docker compose up -d app
          sleep 30
          curl -fsS http://localhost:8000/api/health || (docker compose logs app; exit 1)

      - name: Security scan
        run: |
          docker run --rm aquasec/trivy:latest image \
            --severity HIGH,CRITICAL \
            --exit-code 1 \
            brightify:test || echo "⚠ Vulnerabilities found (non-blocking)"

      - name: Move cache
        run: |
          rm -rf /tmp/.buildx-cache
          mv /tmp/.buildx-cache-new /tmp/.buildx-cache
```

### 13.2 Push to registry (production)

```yaml
# .github/workflows/docker-publish.yml
name: Docker Publish

on:
  push:
    tags: ['v*']

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,format=short

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          platforms: linux/amd64,linux/arm64
```

### 13.3 Deploy workflow (manual approval)

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  workflow_dispatch:
    inputs:
      environment:
        type: choice
        options: [staging, prod]
        required: true
      version:
        required: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}
    steps:
      - uses: actions/checkout@v4

      - name: SSH deploy
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.HOST }}
          username: ${{ secrets.USER }}
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd /opt/brightify
            git fetch && git checkout ${{ inputs.version }}
            export VERSION=${{ inputs.version }}
            docker compose pull
            docker compose -f docker-compose.yml -f docker-compose.${{ inputs.environment }}.yml up -d
            sleep 30
            curl -fsS http://localhost/api/health || exit 1
```

---

## 14. MONITORING & LOGGING

### 14.1 Logging architecture

```
App (loguru, JSON) → stdout
                        ↓
                  Docker json-file driver
                        ↓
                  Log rotation (max-size, max-file)
                        ↓
              Optional: Fluentd / Promtail → Loki / Elasticsearch
```

### 14.2 App-side: loguru JSON config

```python
# logging_config.py
from loguru import logger
import sys
import os

logger.remove()  # remove default handler

if os.environ.get("LOG_LEVEL", "INFO") == "DEBUG":
    logger.add(sys.stdout, level="DEBUG", colorize=True, format="<level>{level}</level> {message}")
else:
    logger.add(sys.stdout, level="INFO", serialize=True)   # JSON output

# In app.py
import logging_config  # ensure side-effect
```

Mọi log call: `logger.info("recommendation_made", extra={"user_session": s, "rec_type": "color"})`.

### 14.3 Docker logging config

```yaml
services:
  app:
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
        labels: "service=app,env=prod"
```

### 14.4 Healthcheck endpoints

Brightify đã có `/api/health`. Verify it checks:
- DB connectivity (cheap ping)
- Model loaded
- Redis ping (after Pillar G)

```python
# api/system.py — đảm bảo health endpoint comprehensive
@router.get("/health")
async def health():
    checks = {
        "status": "healthy",
        "version": "8.0.0",
        "recommender_loaded": _recommender is not None,
        "song_count": _recommender.df.shape[0] if _recommender else 0,
        "has_embeddings": _recommender.embeddings is not None if _recommender else False,
        "db_connected": await check_db_ping(),
        "redis_connected": await check_redis_ping(),
    }
    healthy = all([checks["recommender_loaded"], checks["db_connected"]])
    if not healthy:
        checks["status"] = "degraded"
    return JSONResponse(content=checks, status_code=200 if healthy else 503)
```

### 14.5 Prometheus metrics (optional, advanced)

```python
# pip install prometheus-fastapi-instrumentator
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app)
# → /metrics endpoint
```

Compose service:

```yaml
prometheus:
  image: prom/prometheus:latest
  volumes:
    - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    - prom_data:/prometheus
  command:
    - --config.file=/etc/prometheus/prometheus.yml
  networks:
    - backend

grafana:
  image: grafana/grafana-oss:latest
  environment:
    GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}
  volumes:
    - grafana_data:/var/lib/grafana
    - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards:ro
  ports:
    - "3000:3000"
  networks:
    - frontend
    - backend
```

### 14.6 Sentry (error tracking)

```python
# Optional, in app.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
    )
```

---

## 15. MIGRATION STEPS TỪ HIỆN TẠI

### 15.1 Pre-flight (1-2 ngày)

- [ ] Backup current local PostgreSQL: `pg_dump -U user brightify > backup.sql`.
- [ ] Backup `data/`, `music_files/`, `album_art/`, `artist_images/`, `models_cache/`, `checkpoints/`.
- [ ] Document current env vars from local setup.
- [ ] Test app local một lần cuối, ghi nhận baseline metrics.

### 15.2 Phase 1: Add Docker files (2-3 ngày)

- [ ] Write `Dockerfile` (multi-stage).
- [ ] Write `.dockerignore`.
- [ ] Write `docker-compose.yml` (base).
- [ ] Write `docker-compose.dev.yml`.
- [ ] Add `db/init/01-extensions.sql`.
- [ ] Add `nginx/nginx.conf` + `conf.d/brightify.conf`.
- [ ] Test build: `docker build -t brightify:test .`.
- [ ] Test app boot: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`.

### 15.3 Phase 2: Database migration (1 ngày)

- [ ] Start db service: `docker compose up -d db`.
- [ ] Verify extensions: `docker compose exec db psql -c "\dx"` → vector, pg_trgm.
- [ ] Restore data:
  ```bash
  docker compose exec -T db psql -U brightify -d brightify < backup.sql
  ```
- [ ] Verify counts match local: songs, artists, embeddings.
- [ ] Test HNSW index: `EXPLAIN ANALYZE SELECT ... ORDER BY embedding <=> '...' LIMIT 10;`

### 15.4 Phase 3: App container (1-2 ngày)

- [ ] Update `db/engine.py` để dùng `DATABASE_URL` từ env (đã có).
- [ ] Update `config.py`: `_read_secret_or_env()` cho secrets.
- [ ] Generate `.env` từ `.env.example`.
- [ ] Test full stack: `docker compose up`.
- [ ] Smoke test: open browser http://localhost/, click around.
- [ ] Run backtest from current `tools/backtest.py`, compare với local baseline.

### 15.5 Phase 4: Production setup (2-3 ngày)

- [ ] Provision server (Linux + Docker + Docker Compose v2).
- [ ] Setup DNS (point `brightify.example.com` → server IP).
- [ ] Setup Let's Encrypt cert.
- [ ] Generate prod secrets.
- [ ] Configure prod compose overrides.
- [ ] Deploy: `make prod`.
- [ ] Verify all endpoints respond.
- [ ] Setup DB backup cron.

### 15.6 Phase 5: CI/CD (2-3 ngày)

- [ ] Add `.github/workflows/docker-build.yml`.
- [ ] Add `.github/workflows/docker-publish.yml`.
- [ ] Add image size check + smoke test in CI.
- [ ] Trivy security scan in CI.
- [ ] (Optional) Deploy workflow.

### 15.7 Phase 6: Monitoring (1-2 ngày)

- [ ] Setup structured logging với loguru.
- [ ] Add Prometheus metrics (optional).
- [ ] Setup Grafana dashboard (optional).
- [ ] Sentry DSN config (optional).

### 15.8 Total effort: 9-15 ngày (1 dev), 5-8 ngày (2 dev parallel).

### 15.9 Production deploy runbook (server mới)

**Tiền đề:** Đã setup CI build & publish image lên GHCR (Section 13.2).

#### Bước 1: Provision server

```bash
# Yêu cầu tối thiểu
# - Ubuntu 22.04+ hoặc Debian 12+
# - 8GB RAM, 4 vCPU
# - 100GB disk (50GB cho music + 50GB cho DB/cache/buffer)
# - Docker 24+ và Docker Compose v2

# Cài Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Cài rclone (cho backup)
sudo apt install -y rclone zstd
```

#### Bước 2: Setup directory structure

```bash
# Tạo Brightify root
sudo mkdir -p /opt/brightify
sudo chown $USER:$USER /opt/brightify
cd /opt/brightify

# Clone repo
git clone https://github.com/your-org/brightify.git app
cd app

# Tạo var/ structure
mkdir -p ../var/{runtime/{music_files,album_art,artist_images,checkpoints,processed,essentia_models,annotations,backtest/{ground_truth,baselines,reports},trained_models},volumes/{postgres_data,redis_data,hf_cache},secrets,backups/{db,snapshots,models},logs/{app,nginx,postgres}}

# Set permissions
chmod 700 ../var/secrets
chmod 755 ../var/runtime ../var/volumes ../var/backups ../var/logs
```

#### Bước 3: Configure secrets

```bash
cd /opt/brightify

# Generate secrets
openssl rand -hex 32 > var/secrets/db_password.txt
openssl rand -hex 32 > var/secrets/admin_key.txt
openssl rand -hex 32 > var/secrets/redis_password.txt
chmod 600 var/secrets/*.txt

# Configure rclone cho off-site backup
rclone config   # interactive — setup remote "brightify-backup"
```

#### Bước 4: Configure environment

```bash
cd /opt/brightify/app

# Copy prod env template
cp .env.prod.example .env

# Edit
cat > .env <<EOF
BRIGHTIFY_ROOT=/opt/brightify
COMPOSE_PROJECT_NAME=brightify

# Data paths
MUSIC_FILES_PATH=/opt/brightify/var/runtime/music_files
ALBUM_ART_PATH=/opt/brightify/var/runtime/album_art
ARTIST_IMAGES_PATH=/opt/brightify/var/runtime/artist_images
CHECKPOINTS_PATH=/opt/brightify/var/runtime/checkpoints
PROCESSED_PATH=/opt/brightify/var/runtime/processed
ESSENTIA_MODELS_PATH=/opt/brightify/var/runtime/essentia_models
ANNOTATIONS_PATH=/opt/brightify/var/runtime/annotations
BACKTEST_PATH=/opt/brightify/var/runtime/backtest
TRAINED_MODELS_PATH=/opt/brightify/var/runtime/trained_models
DB_DATA_PATH=/opt/brightify/var/volumes/postgres_data
REDIS_DATA_PATH=/opt/brightify/var/volumes/redis_data
HF_CACHE_PATH=/opt/brightify/var/volumes/hf_cache
LOGS_PATH=/opt/brightify/var/logs
BACKUPS_PATH=/opt/brightify/var/backups

# DB
POSTGRES_USER=brightify
POSTGRES_DB=brightify
# POSTGRES_PASSWORD via secret file

# App
ALLOWED_ORIGINS=https://brightify.example.com
LOG_LEVEL=INFO
HF_HUB_OFFLINE=1                   # Tắt sau khi warmup xong
EOF

chmod 600 .env
```

#### Bước 5: Restore data từ backup

```bash
cd /opt/brightify

# Pull latest backup từ off-site
LATEST_DB=$(rclone lsf brightify-backup:db/ | sort | tail -1)
LATEST_SNAP=$(rclone lsf brightify-backup:snapshots/ | sort | tail -1)
rclone copy brightify-backup:db/$LATEST_DB /tmp/
rclone copy brightify-backup:snapshots/$LATEST_SNAP /tmp/

# Pull music archive (Glacier — chậm, có thể mất giờ)
rclone copy brightify-backup-glacier:music/latest.tar.zst /tmp/

# Extract runtime snapshot
tar -I 'zstd -d' -xf /tmp/$LATEST_SNAP -C /opt/brightify/var/runtime/

# Extract music archive
tar -I 'zstd -d' -xf /tmp/latest.tar.zst -C /opt/brightify/var/runtime/

# Download Essentia models (nếu không có trong snapshot)
bash app/scripts/download-essentia-models.sh
mv app/models_cache/* /opt/brightify/var/runtime/essentia_models/
```

#### Bước 6: Start DB và restore

```bash
cd /opt/brightify/app

# Start DB + Redis
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d db redis

# Wait healthy
until docker compose exec -T db pg_isready -U brightify; do sleep 2; done

# Apply migrations
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate

# Restore DB
gunzip -c /tmp/$LATEST_DB | \
  docker compose exec -T db psql -U brightify -d brightify

# Verify
docker compose exec db psql -U brightify -d brightify -c "
SELECT 'songs' AS table_name, COUNT(*) FROM songs
UNION ALL SELECT 'embeddings', COUNT(*) FROM song_embeddings
UNION ALL SELECT 'artists', COUNT(*) FROM artists;
"
```

#### Bước 7: Warmup model cache

```bash
# Tạm thời cho phép HF download
sed -i 's/HF_HUB_OFFLINE=1/HF_HUB_OFFLINE=0/' .env

docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm app python -c "
from transformers import AutoTokenizer, AutoModel, CLIPModel, CLIPProcessor
AutoTokenizer.from_pretrained('vinai/phobert-base-v2')
AutoModel.from_pretrained('vinai/phobert-base-v2')
CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')
CLIPModel.from_pretrained('openai/clip-vit-base-patch32')
# Sau Plan 1 Pillar A: thêm MERT
print('Models cached')
"

# Reset offline
sed -i 's/HF_HUB_OFFLINE=0/HF_HUB_OFFLINE=1/' .env
```

#### Bước 8: Setup SSL

```bash
cd /opt/brightify/app

# Initial cert (cần DNS đã trỏ về server)
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot \
  certonly --webroot -w /var/www/certbot \
  --email admin@example.com --agree-tos --no-eff-email \
  -d brightify.example.com
```

#### Bước 9: Start full stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Verify
sleep 60   # đợi model load
curl -fsS https://brightify.example.com/api/health
```

#### Bước 10: Setup cron

```bash
sudo cp app/scripts/cron/brightify.cron /etc/cron.d/brightify
sudo chmod 644 /etc/cron.d/brightify
sudo systemctl reload cron
```

#### Bước 11: Setup monitoring (optional)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.monitoring.yml up -d prometheus grafana
```

### 15.10 Post-deploy verification checklist

- [ ] `curl https://brightify.example.com/api/health` → 200, status=healthy
- [ ] Frontend SPA load tại root URL
- [ ] DB count matches backup: songs, embeddings, artists
- [ ] Audio streaming hoạt động (Range request 206)
- [ ] Album art endpoints serve JPG
- [ ] Recommendation endpoints respond < 500ms p95
- [ ] HNSW index used: `EXPLAIN ANALYZE` cho similarity query
- [ ] Backup cron: chạy thử `bash scripts/backup-db.sh` → file xuất hiện
- [ ] Off-site sync: verify file lên S3
- [ ] Healthcheck containers tất cả "healthy" trong `docker compose ps`
- [ ] Logs structured JSON, không có ERROR trong 10 phút đầu
- [ ] Resource usage trong limits (`docker stats`)
- [ ] SSL cert valid: `curl -vI https://brightify.example.com 2>&1 | grep "SSL"`
- [ ] Trivy scan: 0 critical
- [ ] Firewall: chỉ open 80/443 (DB 5432 KHÔNG expose ngoài)

---

## 16. CHECKLIST & SUCCESS CRITERIA

### 16.1 Acceptance checklist

#### Image quality
- [ ] Final image size ≤ 3 GB.
- [ ] Multi-stage build implemented.
- [ ] Non-root user (UID 1000).
- [ ] No `latest` tag in production.
- [ ] `.dockerignore` skips large data + sensitive files.

#### Functionality
- [ ] `docker compose up` start toàn stack without manual intervention.
- [ ] All API endpoints respond (≥ 41 endpoints).
- [ ] Migrations apply correctly.
- [ ] pgvector + pg_trgm extensions active.
- [ ] HNSW index built and used (verify EXPLAIN).
- [ ] Audio streaming works (Range requests).
- [ ] Frontend SPA loads at root URL.

#### Performance
- [ ] Cold start ≤ 120s (PhoBERT + CLIP loaded).
- [ ] API p95 latency không regress vs local.
- [ ] Backtest results match local baseline (±2% tolerance).

#### Security
- [ ] DB không expose port ngoài backend network.
- [ ] Secrets không trong env (prod): dùng `/run/secrets/`.
- [ ] HTTPS enforced via nginx.
- [ ] Security headers (HSTS, X-Frame-Options, ...).
- [ ] Trivy scan: 0 critical, < 5 high (acceptable).
- [ ] Non-root user verified in running container.

#### Operations
- [ ] DB backup cron working.
- [ ] Healthcheck pass cho all services.
- [ ] Logs structured JSON.
- [ ] Resource limits configured.
- [ ] Restart policy: `unless-stopped`.

#### Dev experience
- [ ] Hot reload working trong dev mode.
- [ ] `docker compose logs -f` shows readable output.
- [ ] `make shell`, `make dbshell` convenient access.
- [ ] README updated với Docker quick start.

### 16.2 Success criteria (quantitative)

| Metric | Target |
|---|---|
| Image size | ≤ 3 GB |
| Build time (clean) | ≤ 10 min |
| Build time (cached) | ≤ 2 min |
| Cold start | ≤ 120s |
| Memory footprint (app) | ≤ 4 GB |
| Memory footprint (db) | ≤ 4 GB |
| API latency p95 | ≤ baseline × 1.1 |
| Backup script runtime | ≤ 5 min |
| `docker compose up` to healthy | ≤ 3 min |

---

## 17. TÀI LIỆU THAM KHẢO

### Official docs

- [FastAPI Docker deployment](https://fastapi.tiangolo.com/deployment/docker/)
- [FastAPI Server Workers](https://fastapi.tiangolo.com/deployment/server-workers/)
- [Docker Compose reference](https://docs.docker.com/reference/compose-file/)
- [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/)
- [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/)
- [Postgres Docker official](https://hub.docker.com/_/postgres)
- [pgvector Docker Hub](https://hub.docker.com/r/pgvector/pgvector)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [HuggingFace cache management](https://huggingface.co/docs/huggingface_hub/en/guides/manage-cache)
- [Nginx Docker official](https://hub.docker.com/_/nginx)
- [Let's Encrypt with certbot](https://certbot.eff.org/)

### Best practices articles

- [Crunchy Data — HNSW with Postgres and pgvector](https://www.crunchydata.com/blog/hnsw-indexes-with-postgres-and-pgvector)
- [BetterStack — FastAPI Docker best practices](https://betterstack.com/community/guides/scaling-python/fastapi-docker-best-practices/)
- [TestDriven.io — Dockerizing FastAPI](https://testdriven.io/blog/fastapi-docker-traefik/)
- [pythonspeed — Decoupling migrations from startup](https://pythonspeed.com/articles/schema-migrations-server-startup/)
- [pythonspeed — Docker BuildKit pip caching](https://pythonspeed.com/articles/docker-cache-pip-downloads/)
- [Marton Veges — Optimizing PyTorch Docker images](https://mveg.es/posts/optimizing-pytorch-docker-images-cut-size-by-60percent/)
- [Sysdig — Dockerfile security best practices](https://www.sysdig.com/learn-cloud-native/dockerfile-best-practices)
- [Bind mount vs Named volume benchmark](https://www.codegenes.net/blog/docker-bind-mount-directory-vs-named-volume-performance-comparison/)

### Internal docs

- `docs/PLAN_SYSTEM_UPGRADE.md` — Pillar G includes async SQLAlchemy + Redis (compatible with this plan).
- `docs/PLAN_BACKTEST_METRICS.md` — backtest cần Docker để CI integration.
- `CLAUDE.md` — current project instructions, sẽ cần update Docker workflow.

---

**Hết Plan 3.**
