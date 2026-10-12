"""Compliance from rules.csv. Rule text and sources come from the table, never from the LLM."""


def evaluate(market: str, product_allergens: list[str], product_name: str,
             conflicts: list[dict], rules: list[dict]) -> dict:
    triggered = []
    name = product_name.lower()
    for r in rules:
        if r["market"] != market:
            continue
        t, v = r["trigger_type"], r["trigger_value"].lower()
        hit = (
            (t == "allergen" and product_allergens and (v == "*" or v in product_allergens))
            or (t == "name_term" and v and v in name)
            or (t == "free_from_conflict" and conflicts)
        )
        if hit:
            triggered.append({k: r[k] for k in ("rule_id", "trigger_type", "requirement", "source_url", "verified")})
    return {
        "market": market,
        "allergens_to_declare": product_allergens,
        "triggered_rule_ids": [r["rule_id"] for r in triggered],
        "triggered_rules": triggered,
        "unverified_rule_ids": [r["rule_id"] for r in triggered if not r["verified"]],
    }
