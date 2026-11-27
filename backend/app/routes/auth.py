import base64
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Depends, Header, HTTPException, status as http_status
from pydantic import BaseModel

from app.config import config


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(username: str, role: str = "admin", expires_in_sec: int = None) -> str:
    """Minimal HMAC-SHA256 JWT (no external dependency)."""
    ttl = expires_in_sec or (config.JWT_EXPIRE_MINUTES * 60)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": username, "role": role, "exp": int(time.time()) + ttl}
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(payload).encode())}"
    signature = _b64(hmac.new(config.JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest())
    return f"{signing_input}.{signature}"


def verify_token(token: str) -> dict:
    try:
        header_part, payload_part, sig_part = token.split(".")
        expected = _b64(hmac.new(config.JWT_SECRET.encode(), f"{header_part}.{payload_part}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig_part):
            raise ValueError("bad signature")
        payload = json.loads(_b64d(payload_part))
        if int(payload.get("exp", 0)) < time.time():
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")


def require_admin(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    payload = verify_token(authorization[7:])
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return payload


# ---- FastAPI router ----
router = APIRouter(prefix="/api/auth", tags=["Authentication & Sessions"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginRequest):
    if req.username != config.ADMIN_USERNAME or req.password != config.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(req.username, role="admin")
    return {"status": "success", "token": token, "role": "admin", "username": req.username}


@router.get("/me")
def me(auth: dict = Depends(require_admin)):
    return {"status": "success", "username": auth.get("sub"), "role": auth.get("role")}