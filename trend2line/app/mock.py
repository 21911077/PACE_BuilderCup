"""MOCK_LLM=1 handlers. Lets the team deploy and demo the full flow before an API key exists.

The mock writer deliberately makes mistakes on attempt 1 so the verifier loop is visible offline.
Everything produced here is labelled 'mock' in the API response and the UI.
"""

DUBAI_SPEC = {
    "product_name": "Milk chocolate bar with pistachio cream and toasted kataifi",
    "format": "shell_and_fill",
    "ingredients": [
        {"name": "milk chocolate", "ingredient_id": "milk_chocolate", "role": "shell"},
        {"name": "pistachio paste", "ingredient_id": "pistachio_paste", "role": "filling"},
        {"name": "sugar", "ingredient_id": "sugar", "role": "filling"},
        {"name": "vegetable fat", "ingredient_id": "vegetable_fat", "role": "filling"},
        {"name": "milk powder", "ingredient_id": "milk_powder", "role": "filling"},
        {"name": "kataifi pastry", "ingredient_id": "kataifi", "role": "inclusion"},
        {"name": "butter", "ingredient_id": "butter", "role": "inclusion"},
        {"name": "tahini", "ingredient_id": "tahini", "role": "filling"},
    ],
    "process_steps": ["tempering", "shell_moulding", "toasting", "filling_deposit",
                      "backing_off", "cooling", "demoulding", "wrapping"],
    "notes": "MOCK spec.",
}

DALGONA_SPEC = {
    "product_name": "Ready-to-drink whipped coffee",
    "format": "beverage",
    "ingredients": [
        {"name": "instant coffee", "ingredient_id": "instant_coffee", "role": "base"},
        {"name": "sugar", "ingredient_id": "sugar", "role": "base"},
        {"name": "milk", "ingredient_id": "milk", "role": "base"},
    ],
    "process_steps": ["mixing", "liquid_filling", "cooling"],
    "notes": "MOCK spec.",
}


def deconstruct(prompt: str, ctx: dict) -> dict:
    return DALGONA_SPEC if "dalgona" in ctx.get("trend", "").lower() else DUBAI_SPEC


def pick_article(prompt: str, ctx: dict) -> dict:
    return {"title": ctx.get("title", ""), "reason": "mock"}


def write_plan(prompt: str, ctx: dict) -> dict:
    reg, state, plant, attempt = ctx["reg"], ctx["state"], ctx["plant"], ctx["attempt"]
    d = state["decision"]
    idx = state["evidence_index"]
    tl_id = idx.get(f"timeline_{d['route']}")
    tl = reg.get(tl_id)["payload"]
    cap = tl["capture"]["median"]
    claims = [
        {"text": f"Median capture at launch is {round(cap * 100)}%.", "kind": "numeric",
         "evidence_ids": [tl_id], "field": "capture.median", "value": round(cap * 100)},
        {"text": f"Time to shelf is {tl['total_days']} days.", "kind": "numeric",
         "evidence_ids": [tl_id], "field": "total_days", "value": tl["total_days"]},
        {"text": f"Earliest shelf date is {tl['launch_date']}.", "kind": "date",
         "evidence_ids": [tl_id], "field": "launch_date", "date_value": tl["launch_date"]},
        {"text": "Consumers may prefer a thinner shell.", "kind": "speculative"},
    ]
    comp = reg.get(idx["compliance"])["payload"]
    if comp["triggered_rule_ids"]:
        claims.append({"text": "All allergens must be declared on pack.", "kind": "regulatory",
                       "rule_id": comp["triggered_rule_ids"][0]})
    if d["line"]:
        line = plant["lines"][d["line"]]
        cap_name = line["capabilities"][0]
        claims.append({"text": f"{d['line']} has {cap_name}.", "kind": "process",
                       "line": d["line"], "capability": cap_name, "capability_present": True})
    rationale = (f"{d['verdict']} via {d['route'].replace('_', ' ')}: about {round(cap * 100)}% of current "
                 f"interest remains after {tl['total_days']} days to shelf.")
    if attempt == 1:  # deliberate errors so the verifier has something to catch offline
        wrong_line = next((lid for lid, ln in plant["lines"].items()
                           if "one_shot_depositing" not in ln["capabilities"]), None)
        if wrong_line:
            claims.append({"text": f"{wrong_line} can deposit filled bars.", "kind": "process",
                           "line": wrong_line, "capability": "one_shot_depositing", "capability_present": True})
        rationale += " Pistachio prices rose 60% this year."
    return {"headline": f"{d['verdict']}: {state['trend']}", "rationale": rationale,
            "actions": [f"Lock the route: {d['route'].replace('_', ' ')}.", "Start artwork in parallel with trials."],
            "claims": claims}


MOCK_HANDLERS = {"deconstruct": deconstruct, "pick_article": pick_article, "write_plan": write_plan}
