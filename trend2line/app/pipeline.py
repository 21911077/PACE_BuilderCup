"""Orchestrates the stages. LLM interprets (article, product spec, narrative); code computes everything else."""
import datetime as dt
import time

from . import prompts
from .config import Settings
from .evidence import EvidenceRegistry
from .llm import LLM
from typing import get_args

from .models import ArticleChoice, Plan, ProcessStep, ProductSpec
from .stages import bom as bom_stage
from .stages import catalog, compliance as compliance_stage, feasibility, timeline, trend as trend_stage
from .stages.verifier import feedback_for_writer, verify
STEP_VOCAB = list(get_args(ProcessStep))


class PipelineError(ValueError):
    pass


def _mock_curve(trend: str, as_of: dt.date) -> trend_stage.Series:
    start = as_of - dt.timedelta(days=3 * 365)
    if "dalgona" in trend.lower():
        return trend_stage.synthetic_series(start, as_of, dt.date(2020, 3, 28), 10, 20)
    return trend_stage.synthetic_series(start, as_of, as_of - dt.timedelta(days=20), 150, 90)


def run(trend: str, sku_id: str, as_of: dt.date, market: str, image: tuple[bytes, str] | None,
        llm: LLM, settings: Settings) -> dict:
    t0 = time.time()
    steps: list[dict] = []
    reg = EvidenceRegistry()
    plant = catalog.plant()
    our_sku = plant["our_skus"].get(sku_id)
    if our_sku is None:
        raise PipelineError(f"Unknown SKU {sku_id}")

    def log(name: str, detail: str, kind: str = "code") -> None:
        steps.append({"step": name, "detail": detail, "kind": kind, "t": round(time.time() - t0, 2)})

    # 1. Trend Scout ---------------------------------------------------------
    if settings.mock_llm:
        title, source = trend, "synthetic_mock_curve"
        series = _mock_curve(trend, as_of)
        log("Trend Scout", "MOCK MODE: synthetic pageview curve, not real data.")
    else:
        try:
            candidates = trend_stage.search_candidates(trend, settings.wiki_user_agent)
        except Exception as exc:
            raise PipelineError(f"Wikipedia search failed: {exc}") from exc
        if not candidates:
            raise PipelineError(f"No Wikipedia article found for '{trend}'.")
        title = candidates[0]
        if len(candidates) > 1:
            choice = llm.structured("pick_article", prompts.pick_article(trend, candidates), ArticleChoice)
            title = choice.title if choice.title in candidates else candidates[0]
            log("Trend Scout", f"Gemini chose '{title}' from {len(candidates)} candidates.", "llm")
        series = trend_stage.fetch_pageviews(title, as_of - dt.timedelta(days=3 * 365), as_of,
                                             settings.wiki_user_agent)
        source = "wikimedia_pageviews"
    report = trend_stage.analyze(series, as_of, catalog.fad_reference())
    if report["stage"] == "insufficient_data":
        raise PipelineError(f"Not enough pageview history for '{title}'.")
    ev_trend = reg.record(source, title, {"article": title, **report})
    log("Trend Scout", f"{title}: stage {report['stage']}, momentum {report['momentum_90d']}.")

    # 2. Product Deconstructor ----------------------------------------------
    amap = catalog.allergen_map()
    spec = llm.structured("deconstruct", prompts.deconstruct(trend, sorted(amap), STEP_VOCAB), ProductSpec,
                          image=image, mock_context={"trend": trend})
    ev_spec = reg.record("gemini_product_spec", trend, spec.model_dump())
    log("Product Deconstructor", f"{spec.product_name}: {len(spec.ingredients)} ingredients.", "llm")

    # 3. BOM Morph ------------------------------------------------------------
    bom = bom_stage.bom_diff(our_sku, spec, amap)
    ev_bom = reg.record("bom_diff", sku_id, bom)
    log("BOM Morph", f"Adds {', '.join(bom['added_ingredients']) or 'nothing'}.")

    # 4. Line feasibility + allergen blast radius ---------------------------
    cfg = catalog.timeline_cfg()
    product_allergens = set(bom["product_allergens"])
    assessments = [
        feasibility.assess_line(lid, line, list(spec.process_steps), product_allergens,
                                catalog.process_map(), catalog.equipment_catalog(),
                                cfg["in_house"]["allergen_cleaning_validation"])
        for lid, line in plant["lines"].items()
    ]
    ranked = feasibility.rank_lines(assessments)
    best = ranked[0]
    ev_lines = reg.record("plant_yaml", "line assessment",
                          {"recommended_line": best["line_id"], "lines": {a["line_id"]: a for a in ranked}})
    blast = [c for a in assessments for c in a["free_from_conflicts"]]
    log("Line Feasibility", f"Best line {best['line_id']}; {len(blast)} free-from conflicts across lines.")

    # 5. Compliance -------------------------------------------------------------
    comp = compliance_stage.evaluate(market, bom["product_allergens"], f"{trend} {spec.product_name}",
                                     best["free_from_conflicts"], catalog.rules())
    ev_comp = reg.record("rules_csv", market, comp)
    log("Compliance", f"{len(comp['triggered_rule_ids'])} rules triggered.")

    # 6. Timeline and launch window -------------------------------------------
    hl = report["reference_half_life_days"]
    sustained = report["stage"] == "sustained"

    def route_eval(route: str, line: dict | None) -> dict:
        tasks = timeline.build_route(route, cfg, line["gap_lead_days"] if line else 0,
                                     bool(line and line["needs_cleaning_validation"]))
        sched = timeline.schedule(tasks)
        cap = {k: (1.0 if sustained else trend_stage.capture_share(sched["total_days"], v)) for k, v in hl.items()}
        return {"route": route, "line": line["line_id"] if line else None, **sched,
                "launch_date": timeline.launch_date(as_of, sched["total_days"]), "capture": cap}

    routes = []
    if best["feasible"]:
        routes.append(route_eval("in_house", best))
    routes.append(route_eval("co_manufacturer", None))
    route_ids = {r["route"]: reg.record("timeline", r["route"], r) for r in routes}

    # Decision (code, not LLM) -------------------------------------------------
    hard = []
    if best["free_from_conflicts"]:
        hard.append(f"Best in-house line {best['line_id']} would void free-from claims.")
    thresholds = cfg["decision"]
    in_house = next((r for r in routes if r["route"] == "in_house"), None)
    co_man = next(r for r in routes if r["route"] == "co_manufacturer")
    # Prefer our own line (margin, control) unless a co-manufacturer wins clearly on capture.
    margin = thresholds.get("prefer_in_house_within", 0.10)
    if in_house and not hard and co_man["capture"]["median"] - in_house["capture"]["median"] <= margin:
        chosen = in_house
    else:
        chosen = co_man
    c = chosen["capture"]["median"]
    verdict = "GO" if c >= thresholds["go_capture"] else "CONDITIONAL" if c >= thresholds["conditional_capture"] else "NO-GO"
    if verdict == "GO" and (hard or bom["unmapped_ingredients"] or report["reference_status"] != "computed"):
        verdict = "CONDITIONAL"
    decision = {"verdict": verdict, "route": chosen["route"], "line": chosen["line"],
                "capture_median": c, "hard_failures": hard,
                "downgrade_reasons": [r for r, on in [
                    ("unmapped ingredients need review", bool(bom["unmapped_ingredients"])),
                    ("half-life reference is a placeholder", report["reference_status"] != "computed"),
                ] if on]}
    ev_decision = reg.record("decision_rules", "timeline.yaml thresholds", decision)
    log("Decision", f"{verdict} via {chosen['route']} (capture {c}).")

    # 7. Writer + verifier loop ------------------------------------------------
    state = {"trend": trend, "sku": sku_id, "as_of": as_of.isoformat(), "market": market,
             "evidence_index": {"trend": ev_trend, "spec": ev_spec, "bom": ev_bom, "lines": ev_lines,
                                "compliance": ev_comp, "decision": ev_decision, **{f"timeline_{k}": v for k, v in route_ids.items()}},
             "decision": decision}
    attempts, feedback, plan, ver = [], None, None, None
    for attempt in range(1, settings.max_writer_attempts + 1):
        plan = llm.structured("write_plan", prompts.write_plan(state, reg.for_prompt(), feedback), Plan,
                              mock_context={"attempt": attempt, "reg": reg, "state": state, "plant": plant})
        ver = verify(plan, reg, plant, comp, bom)
        rejected = [{"text": x["text"], "reason": x["reason"]} for x in ver["claims"] if x["status"] == "failed"]
        rejected += [{"text": o["text"], "reason": o["reason"]} for o in ver["orphans"]]
        rejected += [{"text": h, "reason": "hard failure"} for h in ver["hard_failures"]
                     if not any(h.startswith(r["text"]) for r in rejected)]
        attempts.append({"attempt": attempt, "trust": ver["trust"], "passed": ver["passed"], "rejected": rejected,
                         "failed": sum(1 for x in ver["claims"] if x["status"] == "failed") + len(ver["orphans"]),
                         "hard_failures": len(ver["hard_failures"])})
        log("Verifier", f"Attempt {attempt}: trust {ver['trust']}, passed={ver['passed']}.", "llm")
        if ver["passed"]:
            break
        feedback = feedback_for_writer(ver)

    return {
        "mode": "mock" if settings.mock_llm else "live",
        "trend": report | {"article": title, "source": source},
        "spec": spec.model_dump(),
        "bom": bom,
        "lines": ranked,
        "allergen_blast_radius": blast,
        "compliance": comp,
        "routes": routes,
        "decision": decision,
        "plan": plan.model_dump() if plan else None,
        "verification": ver,
        "attempts": attempts,
        "evidence": reg.items,
        "steps": steps,
        "llm_calls": llm.calls,
        "cache_hits": llm.cache_hits,
    }
