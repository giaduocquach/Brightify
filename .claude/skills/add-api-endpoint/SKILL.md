---
name: add-api-endpoint
description: Add a new API endpoint to Brightify. Use when creating new routes for music, recommendations, or system APIs.
---

# Add API Endpoint

## File Selection
- Music/browse/search/stream → `api/music.py`
- AI recommendations → `api/recommend.py`
- Health/stats/admin → `api/system.py`
- Auth/login → `api/auth.py`
- Playlist operations → `api/playlist.py`

## Template

```python
@router.get("/api/<endpoint>")
async def endpoint_name(param: str = Query(...)):
    """Endpoint description."""
    try:
        # Business logic
        result = ...
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

## Checklist
1. Add route to appropriate file in `api/`
2. Follow existing response format: `{"status": "success", "data": ...}`
3. Add input validation via Pydantic/Query params
4. Add rate limiting if public-facing (see `api/rate_limit.py`)
5. Admin endpoints: require `X-Admin-Key` header, compare with `hmac.compare_digest()`
6. Test the endpoint manually or add to `test/`

## DataFrame Responses
For endpoints returning song/artist data:
```python
from api.utils import dataframe_to_dict
return dataframe_to_dict(df)
```

## Arguments
$ARGUMENTS
