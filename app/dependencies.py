from fastapi import Header, HTTPException

from .config import API_TOKEN


def require_token(authorization: str | None = Header(default=None)) -> None:
    if not API_TOKEN:
        return
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token")
