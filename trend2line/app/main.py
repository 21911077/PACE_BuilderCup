"""FastAPI entrypoint for Cloud Run. Cloud Run sets $PORT; the Dockerfile passes it to uvicorn."""
import datetime as dt
import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import pipeline
from .config import STATIC_DIR, get_settings
from .llm import LLM, LLMError
from .mock import MOCK_HANDLERS
from .stages import catalog

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("trend2line")
app = FastAPI(title="Trend2Line", version="0.1.0")
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
def config() -> dict:
    s = get_settings()
    ref = catalog.fad_reference()
    return {"mock": s.mock_llm, "model": s.gemini_model or None, "auth": "vertex" if s.use_vertex else "api_key",
            "reference_status": ref.get("status"), "skus": {k: v["name"] for k, v in catalog.plant()["our_skus"].items()},
            "markets": sorted({r["market"] for r in catalog.rules()})}


@app.post("/api/run")
def run(trend: str = Form(..., min_length=2, max_length=120), sku_id: str = Form(...),
        as_of: str = Form(...), market: str = Form("IN"), image: UploadFile | None = File(None)) -> dict:
    s = get_settings()
    try:
        as_of_date = dt.date.fromisoformat(as_of)
    except ValueError:
        raise HTTPException(400, "as_of must be YYYY-MM-DD")
    if as_of_date > dt.date.today():
        raise HTTPException(400, "as_of cannot be in the future")
    img = None
    if image is not None and image.filename:
        if image.content_type not in ALLOWED_MIME:
            raise HTTPException(400, f"Image type {image.content_type} not supported")
        data = image.file.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(400, "Image larger than 8 MB")
        img = (data, image.content_type)
    llm = LLM(s, MOCK_HANDLERS)
    try:
        return pipeline.run(trend.strip(), sku_id, as_of_date, market, img, llm, s)
    except pipeline.PipelineError as exc:
        raise HTTPException(400, str(exc))
    except LLMError as exc:
        log.exception("LLM failure")
        raise HTTPException(503, str(exc))
