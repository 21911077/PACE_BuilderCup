import datetime as dt
import os

os.environ["MOCK_LLM"] = "1"
os.environ["CACHE_DIR"] = "/tmp/t2l_test_cache"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.evidence import EvidenceRegistry  # noqa: E402
from app.main import app  # noqa: E402
from app.mock import DUBAI_SPEC  # noqa: E402
from app.models import Claim, Plan, ProductSpec  # noqa: E402
from app.stages import bom, catalog, feasibility, timeline, trend  # noqa: E402
from app.stages.verifier import verify  # noqa: E402

SPEC = ProductSpec.model_validate(DUBAI_SPEC)


def test_trend_stage_and_half_life():
    start, peak = dt.date(2022, 1, 1), dt.date(2023, 6, 1)
    s = trend.synthetic_series(start, dt.date(2024, 1, 1), peak, rise_days=10, half_life=20)
    rep = trend.analyze(s, dt.date(2023, 8, 1), catalog.fad_reference())
    assert rep["stage"] == "decaying"
    assert rep["reference_class"] == "flash"
    assert 15 <= rep["observed_half_life_days"] <= 30
    rising = trend.analyze(s, dt.date(2023, 5, 29), catalog.fad_reference())
    assert rising["stage"] in {"rising", "peaking"}


def test_capture_formula():
    assert trend.capture_share(120, 120) == 0.5
    assert trend.capture_share(90, 30) == 0.125


def test_bom_adds_allergens():
    d = bom.bom_diff(catalog.plant()["our_skus"]["CLASSIC-100"], SPEC, catalog.allergen_map())
    assert {"tree_nuts", "wheat", "sesame"} <= set(d["new_allergens_vs_our_sku"])
    assert d["format_change"] is True


def test_allergen_blast_radius_and_line_choice():
    allergens = set(bom.bom_diff(catalog.plant()["our_skus"]["CLASSIC-100"], SPEC, catalog.allergen_map())["product_allergens"])
    res = {lid: feasibility.assess_line(lid, ln, list(SPEC.process_steps), allergens, catalog.process_map(),
                                        catalog.equipment_catalog(), 14)
           for lid, ln in catalog.plant()["lines"].items()}
    assert any(c["sku_id"] == "KIDS-NF-40" for c in res["L2"]["free_from_conflicts"])
    assert any(c["sku_id"] == "GF-BITES-25" for c in res["L4"]["free_from_conflicts"])
    assert feasibility.rank_lines(list(res.values()))[0]["line_id"] == "L3"


def test_timeline_longest_path():
    cfg = catalog.timeline_cfg()
    assert timeline.schedule(timeline.build_route("co_manufacturer", cfg))["total_days"] == 55
    s = timeline.schedule(timeline.build_route("in_house", cfg, gap_days=21, needs_validation=True))
    assert s["total_days"] == 21 + 10 + 14 + 7 + 10
    assert s["critical_path"][0] == "gap_resolution"


def _setup_reg():
    reg = EvidenceRegistry()
    eid = reg.record("timeline", "x", {"total_days": 62, "launch_date": "2025-05-02", "capture": {"median": 0.7}})
    comp = {"triggered_rule_ids": ["IN-ALLERGEN-DECL"], "unverified_rule_ids": ["IN-ALLERGEN-DECL"]}
    b = {"new_allergens_vs_our_sku": ["tree_nuts"]}
    return reg, eid, comp, b


def test_verifier_catches_wrong_number_orphan_and_process():
    reg, eid, comp, b = _setup_reg()
    plan = Plan(headline="GO", rationale="Prices rose 60% and capture is 70%.", actions=[], claims=[
        Claim(text="capture 70%", kind="numeric", evidence_ids=[eid], field="capture.median", value=70),
        Claim(text="62 days", kind="numeric", evidence_ids=[eid], field="total_days", value=55),
        Claim(text="L2 deposits", kind="process", line="L2", capability="one_shot_depositing", capability_present=True),
        Claim(text="launch", kind="date", evidence_ids=[eid], field="launch_date", date_value="2025-05-02"),
    ])
    v = verify(plan, reg, catalog.plant(), comp, b)
    st = {c["text"]: c["status"] for c in v["claims"]}
    assert st == {"capture 70%": "verified", "62 days": "failed", "L2 deposits": "failed", "launch": "verified"}
    assert [o["text"] for o in v["orphans"]] == ["60%"]
    assert v["hard_failures"] and not v["passed"]


def test_verifier_blocks_no_new_allergens_claim():
    reg, eid, comp, b = _setup_reg()
    plan = Plan(headline="GO", rationale="There are no new allergens.", actions=[], claims=[])
    assert verify(plan, reg, catalog.plant(), comp, b)["hard_failures"]


def test_end_to_end_mock_api():
    c = TestClient(app)
    assert c.get("/healthz").json() == {"ok": True}
    r = c.post("/api/run", data={"trend": "Dubai chocolate", "sku_id": "CLASSIC-100",
                                 "as_of": "2025-03-01", "market": "IN"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] == "mock"
    assert j["decision"]["line"] == "L3"
    assert j["attempts"][0]["passed"] is False      # mock writer errs on purpose
    assert j["attempts"][-1]["passed"] is True      # verifier loop fixed it
    assert j["decision"]["verdict"] in {"CONDITIONAL", "NO-GO"}  # placeholder reference caps GO
    d = c.post("/api/run", data={"trend": "Dalgona coffee", "sku_id": "CLASSIC-100",
                                 "as_of": "2020-04-05", "market": "IN"}).json()
    assert d["routes"][-1]["route"] == "co_manufacturer"
    assert all(r["route"] != "in_house" for r in d["routes"])  # no in-house liquid filling


def test_settings_default_mock():
    assert get_settings().mock_llm is True
