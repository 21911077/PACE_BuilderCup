"""Line feasibility and the allergen blast radius. Set logic over plant.yaml, no LLM."""

FREE_FROM_ALLERGENS = {
    "nut_free": ["tree_nuts", "peanut"],
    "gluten_free": ["wheat"],
    "dairy_free": ["milk"],
    "egg_free": ["egg"],
    "sesame_free": ["sesame"],
    "soy_free": ["soy"],
}


def assess_line(line_id: str, line: dict, steps: list[str], product_allergens: set[str],
                process_map: dict[str, list[str]], catalog: dict[str, list[dict]],
                validation_days: int) -> dict:
    caps = set(line["capabilities"])
    gaps, seen = [], set()
    for step in steps:
        if step == "other":
            continue
        required = process_map.get(step)
        if required is None:
            gaps.append({"step": step, "required_any": [], "best_option": None, "unknown_step": True})
            continue
        if caps & set(required) or tuple(required) in seen:
            continue
        seen.add(tuple(required))
        options = sorted((o | {"capability": c} for c in required for o in catalog.get(c, [])),
                         key=lambda o: o["lead_time_days"])
        gaps.append({"step": step, "required_any": required,
                     "best_option": options[0] if options else None, "options": options})

    new_allergens = sorted(product_allergens - set(line["allergens_present"]))
    conflicts = []
    for sku_id, sku in (line.get("skus") or {}).items():
        for claim in sku.get("free_from", []):
            hit = sorted(set(FREE_FROM_ALLERGENS.get(claim, [])) & product_allergens)
            if hit:
                conflicts.append({"sku_id": sku_id, "sku_name": sku["name"], "claim": claim, "allergens": hit})

    unresolvable = [g["step"] for g in gaps if g["best_option"] is None]
    gap_days = max((g["best_option"]["lead_time_days"] for g in gaps if g["best_option"]), default=0)
    needs_validation = bool(new_allergens)
    return {
        "line_id": line_id,
        "line_name": line.get("name", line_id),
        "gaps": gaps,
        "gap_lead_days": gap_days,
        "unresolvable_steps": unresolvable,
        "new_allergens_on_line": new_allergens,
        "needs_cleaning_validation": needs_validation,
        "free_from_conflicts": conflicts,
        "feasible": not unresolvable,
        "score": [len(conflicts), len(unresolvable), gap_days + (validation_days if needs_validation else 0),
                  len(new_allergens)],
    }


def rank_lines(assessments: list[dict]) -> list[dict]:
    """Fewest free-from conflicts, then resolvable, then fastest, then fewest new allergens."""
    return sorted(assessments, key=lambda a: a["score"])
