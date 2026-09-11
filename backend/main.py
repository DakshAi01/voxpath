from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import time
from dotenv import load_dotenv
import sys
import io
from contextlib import asynccontextmanager, AsyncExitStack
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from logging_config import setup_logging, get_logger, new_trace_id
from mcp_server import mcp
import agent
import news_scheduler
import services


if sys.platform == "win32":
    # psycopg's async driver cannot run on Windows' default ProactorEventLoop.
    # Set the policy before any loop exists; asyncio.run() (pytest, TestClient)
    # honours it. uvicorn needs the extra handling in __main__ below.
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

load_dotenv()
setup_logging()
log = get_logger("voxpath.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Own the app-lifetime resources: the Postgres pool and the news scheduler.

    The connection pool is opened once here and held for the process's life.
    Opening a connection per request passes every test and then falls over the
    moment real traffic arrives, so the saver and store are handed this one pool
    rather than being built with their own from_conn_string() helpers (which
    open a single bare connection, not a pool).
    """
    log.info("starting VoxPath API")
    async with AsyncExitStack() as stack:
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            import asyncio

            if type(asyncio.get_running_loop()).__name__ == "ProactorEventLoop":
                raise RuntimeError(
                    "psycopg async cannot run on Windows' ProactorEventLoop. "
                    "Start the server via `python main.py` (which selects a "
                    "SelectorEventLoop) rather than `uvicorn main:app`."
                )
            pool = await stack.enter_async_context(
                AsyncConnectionPool(
                    database_url,
                    min_size=int(os.getenv("DB_POOL_MIN_SIZE", "1")),
                    max_size=int(os.getenv("DB_POOL_MAX_SIZE", "10")),
                    # Open inside the context manager, not in the constructor.
                    open=False,
                    kwargs={
                        # LangGraph issues its own transactions; an outer one would nest.
                        "autocommit": True,
                        # Pooled connections rotate, so server-side prepares don't pay off.
                        "prepare_threshold": 0,
                        "row_factory": dict_row,
                    },
                )
            )
            saver = AsyncPostgresSaver(conn=pool)
            store = AsyncPostgresStore(conn=pool)
            # Idempotent DDL: creates the checkpoint/store tables on first boot.
            await saver.setup()
            await store.setup()
            agent.set_persistence(saver, store)
            log.info("postgres persistence ready (pool max_size=%d)", pool.max_size)
        else:
            log.warning("DATABASE_URL not set - running without conversation persistence")

        news_scheduler.start()
        yield
        await news_scheduler.stop()
    log.info("VoxPath API stopped")


app = FastAPI(title="VoxPath API", lifespan=lifespan)


@app.middleware("http")
async def trace_requests(request: Request, call_next):
    """Assign a trace id to each HTTP request and log method, status, duration."""
    new_trace_id()
    start = time.perf_counter()
    log.info("--> %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        elapsed = (time.perf_counter() - start) * 1000
        log.exception("xxx %s %s failed after %.1f ms", request.method, request.url.path, elapsed)
        raise
    elapsed = (time.perf_counter() - start) * 1000
    log.info("<-- %s %s %s (%.1f ms)", request.method, request.url.path, response.status_code, elapsed)
    return response

# Use a restricted list of origins for CORS in production
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str | None = None


def is_quota_error(error: Exception) -> bool:
    error_text = str(error).upper()
    return "RESOURCE_EXHAUSTED" in error_text or "QUOTA" in error_text or "429" in error_text


def build_fallback_text(user_text: str | None) -> str:
    return services.build_fallback_text(user_text)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/news/status")
async def news_status():
    """Background news-refresher status (last refresh age, interval)."""
    return news_scheduler.status()


app.mount("/mcp", mcp.http_app(path="/"))


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        user_text = request.message

        if not user_text:
            log.warning("chat request with empty message")
            return JSONResponse(status_code=400, content={"error": "No input"})

        log.info("chat request: %r", user_text[:120])

        try:
            text_content = await agent.agent_chat(user_text)
        except Exception as routing_error:
            if is_quota_error(routing_error):
                log.warning("chat hit quota/rate limit, serving fallback: %s", routing_error)
                fallback_text = build_fallback_text(user_text)
                return JSONResponse(
                    content={
                        "text": fallback_text,
                        "audio": None,
                    }
                )
            log.exception("chat agent failed: %s", routing_error)
            return JSONResponse(status_code=500, content={"error": str(routing_error)})

        log.info("chat reply (%d chars): %r", len(text_content), text_content[:120])

        return JSONResponse(
            content={
                "text": text_content,
                "audio": None,
            }
        )

    except Exception as error:
        log.exception("chat endpoint failed: %s", error)
        return JSONResponse(status_code=500, content={"error": str(error)})


if __name__ == "__main__":
    import asyncio

    import uvicorn

    # log_config=None keeps our logging_config setup instead of uvicorn's defaults.
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_config=None)
    server = uvicorn.Server(config)
    if sys.platform == "win32":
        # uvicorn builds its loop from a factory hardcoded to ProactorEventLoop on
        # win32, ignoring the policy set above, so run serve() on our own loop.
        asyncio.run(server.serve())
    else:
        server.run()
