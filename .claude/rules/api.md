---
paths:
  - "api/**/*.py"
  - "app.py"
---

# API Development Rules

## Route Conventions
- All routes under `/api/` prefix
- Music endpoints: `/api/songs`, `/api/artists`, `/api/albums`, `/api/search`
- Recommendation endpoints: `/api/recommend/*`
- System endpoints: `/api/health`, `/api/stats`

## Security
- Admin key: always compare with `hmac.compare_digest()` — never use `==`
- Rate limiting: sliding-window per IP, configurable per endpoint
- `X-Forwarded-For` should be validated against known proxy IPs in production
- Image uploads: set `PIL.Image.MAX_IMAGE_PIXELS = 25_000_000`

## Response Format
- Use `dataframe_to_dict()` from `api/utils.py` for DataFrame→JSON conversion
- Include proper HTTP status codes and error messages
- Stream audio via `/api/stream/{song_id}` with range request support

## FastAPI Patterns
- Use `FastAPI(lifespan=...)` for startup/shutdown events
- Prefer `FastAPI Depends()` for dependency injection
- CORS configured in `app.py` — do not add per-route CORS
