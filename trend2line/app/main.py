"""FastAPI entrypoint for Cloud Run. Cloud Run sets $PORT; the Dockerfile passes it to uvicorn."""
import datetime as dt
import logging

import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import pipeline
from .config import DATA_DIR, STATIC_DIR, get_settings
from .llm import LLM, LLMError
from .mock import MOCK_HANDLERS
from .stages import catalog

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("trend2line")
app = FastAPI(title="Trend2Line", version="0.2.0")
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PLANT_BYTES = 256 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}


def _plant_from_upload(upload: UploadFile | None) -> dict | None:
    if upload is None or not upload.filename:
        return None
    raw = upload.file.read(MAX_PLANT_BYTES + 1)
    if len(raw) > MAX_PLANT_BYTES:
        raise HTTPException(400, "Plant file larger than 256 KB")
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("top level must be a mapping")
        return catalog.prepare_plant({**data, "provenance": data.get("provenance", "uploaded_company_input")})
    except (ValueError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise HTTPException(400, f"Plant file is not valid: {exc}")


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
    plant = catalog.default_plant()
    mk = catalog.markets()["markets"]
    return {
        "mode": "offline" if s.offline else ("mock_llm" if s.mock_llm else "live"),
        "model": s.gemini_model or None,
        "auth": s.resolved_auth,
        "reference_status": ref.get("status"),
        "data_refreshed_at": catalog.manifest().get("refreshed_at"),
        "company": plant.get("company"),
        "home_market": plant.get("home_market"),
        "skus": {k: f"{v['name']} ({v['line']})" for k, v in plant["skus"].items()},
        "markets": {k: {"name": v["name"], "status": v["allergen_source"]["status"]} for k, v in mk.items()},
        "demo_trends": [{k: str(d[k]) for k in ("trend", "origin", "suggested_as_of", "suggested_market")}
                        for d in catalog.demo_trends()],
        "today": dt.date.today().isoformat(),
    }


@app.get("/api/provenance")
def provenance() -> dict:
    mk = catalog.markets()["markets"]
    return {
        "manifest": catalog.manifest(),
        "fad_reference": {k: v for k, v in catalog.fad_reference().items() if k != "fads"},
        "markets": {k: {"name": v["name"], "allergen_source": {a: str(b) for a, b in v["allergen_source"].items()},
                        "rules": [{"rule_id": r["rule_id"], **r["source"]} for r in v["rules"]]}
                    for k, v in mk.items()},
    }


@app.get("/api/plant/template")
def plant_template() -> FileResponse:
    return FileResponse(DATA_DIR / "plant.yaml", media_type="text/yaml", filename="plant.yaml")


@app.post("/api/plant/validate")
def plant_validate(plant_file: UploadFile = File(...)) -> dict:
    plant = _plant_from_upload(plant_file)
    return {"company": plant.get("company"), "skus": {k: f"{v['name']} ({v['line']})" for k, v in plant["skus"].items()},
            "lines": {k: {"name": v.get("name", k), "allergens_present": v["allergens_present"]}
                      for k, v in plant["lines"].items()}}


@app.post("/api/run")
def run(trend: str = Form(..., min_length=2, max_length=120), sku_id: str = Form(...),
        as_of: str = Form(...), market: str = Form(""), scan: bool = Form(True),
        image: UploadFile | None = File(None), plant_file: UploadFile | None = File(None)) -> dict:
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
    plant = _plant_from_upload(plant_file)
    market = market or (plant or catalog.default_plant()).get("home_market") or next(iter(catalog.markets()["markets"]))
    llm = LLM(s, MOCK_HANDLERS)
    try:
        return pipeline.run(trend.strip(), sku_id, as_of_date, market, img, llm, s, plant=plant, scan=scan)
    except pipeline.PipelineError as exc:
        raise HTTPException(400, str(exc))
    except LLMError as exc:
        log.exception("LLM failure")
        raise HTTPException(503, str(exc))
