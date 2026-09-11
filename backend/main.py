from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import time
from dotenv import load_dotenv
import sys
import io
from contextlib import asynccontextmanager
from logging_config import setup_logging, get_logger, new_trace_id
from mcp_server import mcp
import agent
import news_scheduler
import services


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
    log.info("starting VoxPath API")
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
    import uvicorn

    # log_config=None keeps our logging_config setup instead of uvicorn's defaults.
    uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None)
