"""Email and password authentication for VoxPath.

Identity is the foundation the memory system needs: until a request carries a
verified user, every conversation and every stored memory shares one bucket.
So the only thing that may set a user id is a token this module signed -- never
a request field, a tool argument, or anything the model produced.

Deliberately local: users live in the same Postgres the agent already uses, so
there is no third-party account to configure. Swapping in a hosted identity
provider later means replacing `current_user` and leaving the rest alone.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

from logging_config import get_logger

log = get_logger("voxpath.auth")

# Tokens are signed with this. A changed secret invalidates every existing
# session, which is the intended way to force everyone to sign in again.
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "168"))  # one week

# bcrypt truncates silently past 72 bytes, so a longer password would make the
# tail meaningless. Reject it instead of pretending it counted.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_CHARS = 8

_pool = None
_bearer = HTTPBearer(auto_error=False)


class User(BaseModel):
    id: str
    email: str


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_CHARS)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User


async def setup(pool) -> None:
    """Create the users table and keep the pool for later queries."""
    global _pool
    _pool = pool
    async with pool.connection() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            text PRIMARY KEY,
                email         text UNIQUE NOT NULL,
                password_hash text NOT NULL,
                created_at    timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        # Threads are owned, so one signed-in user cannot read another's
        # conversation by guessing or stealing a thread id.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS threads (
                thread_id  text PRIMARY KEY,
                owner_id   text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at timestamptz NOT NULL DEFAULT now(),
                last_used  timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    if not JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET is not set. Generate one with "
            "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"` "
            "and add it to backend/.env"
        )
    log.info("auth ready (token ttl %dh)", TOKEN_TTL_HOURS)


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at most {MAX_PASSWORD_BYTES} bytes.",
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")[:MAX_PASSWORD_BYTES]
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def register(creds: Credentials) -> TokenResponse:
    user_id = f"u_{uuid.uuid4().hex[:16]}"
    email = creds.email.lower().strip()
    password_hash = hash_password(creds.password)
    async with _pool.connection() as conn:
        existing = await (await conn.execute("SELECT 1 FROM users WHERE email = %s", (email,))).fetchone()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "That email is already registered.")
        await conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (%s, %s, %s)",
            (user_id, email, password_hash),
        )
    user = User(id=user_id, email=email)
    log.info("registered %s", email)
    return TokenResponse(access_token=create_token(user), user=user)


async def login(creds: Credentials) -> TokenResponse:
    email = creds.email.lower().strip()
    async with _pool.connection() as conn:
        row = await (
            await conn.execute("SELECT id, password_hash FROM users WHERE email = %s", (email,))
        ).fetchone()
    # One message for both "no such account" and "wrong password", so the
    # endpoint cannot be used to discover which emails are registered.
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if not row or not verify_password(creds.password, row["password_hash"]):
        log.warning("failed login for %s", email)
        raise invalid
    user = User(id=row["id"], email=email)
    log.info("login %s", email)
    return TokenResponse(access_token=create_token(user), user=user)


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """The signed-in user, or 401. The only trusted source of a user id."""
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        return decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Session expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise unauthorized


def decode_token(token: str) -> User:
    """Verify a token this module signed. Raises jwt.InvalidTokenError otherwise."""
    if not JWT_SECRET:
        # An empty key verifies tokens anyone can forge; refuse rather than accept.
        raise jwt.InvalidTokenError("JWT_SECRET is not set")
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    user_id, email = payload.get("sub"), payload.get("email")
    if not user_id or not email:
        raise jwt.InvalidTokenError("token is missing sub or email")
    return User(id=user_id, email=email)


def require_token(app):
    """Wrap a mounted ASGI app so every HTTP request needs a valid bearer token.

    Mounted sub-apps sit outside FastAPI's dependency system, so `current_user`
    cannot guard them; this does the same check at the ASGI layer.
    """

    async def guarded(scope, receive, send):
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        header = dict(scope.get("headers") or []).get(b"authorization", b"").decode("latin-1")
        scheme, _, token = header.partition(" ")
        try:
            if scheme.lower() != "bearer" or not token:
                raise jwt.InvalidTokenError("missing bearer token")
            decode_token(token)
        except jwt.InvalidTokenError:
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer"),
                ],
            })
            await send({"type": "http.response.body", "body": b'{"detail":"Not authenticated."}'})
            return
        await app(scope, receive, send)

    return guarded


async def claim_thread(thread_id: str, user: User) -> None:
    """Record ownership on first use; refuse someone else's thread.

    Returns 404 rather than 403 for a thread owned by another user: a 403 would
    confirm the thread exists, which is itself a small leak.
    """
    async with _pool.connection() as conn:
        row = await (
            await conn.execute("SELECT owner_id FROM threads WHERE thread_id = %s", (thread_id,))
        ).fetchone()
        if row is None:
            await conn.execute(
                "INSERT INTO threads (thread_id, owner_id) VALUES (%s, %s) "
                "ON CONFLICT (thread_id) DO NOTHING",
                (thread_id, user.id),
            )
            return
        if row["owner_id"] != user.id:
            log.warning("user %s tried to use thread owned by %s", user.id, row["owner_id"])
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
        await conn.execute(
            "UPDATE threads SET last_used = now() WHERE thread_id = %s", (thread_id,)
        )
