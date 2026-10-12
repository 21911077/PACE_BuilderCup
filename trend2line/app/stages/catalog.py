"""Loads the knowledge tables. These are authoritative: the LLM never invents their contents."""
import csv
import json
from functools import lru_cache

import yaml

from ..config import DATA_DIR


def _csv(name: str) -> list[dict]:
    with open(DATA_DIR / name, newline="", encoding="utf-8") as f:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


@lru_cache
def plant() -> dict:
    return yaml.safe_load((DATA_DIR / "plant.yaml").read_text())


@lru_cache
def timeline_cfg() -> dict:
    return yaml.safe_load((DATA_DIR / "timeline.yaml").read_text())


@lru_cache
def fad_reference() -> dict:
    return json.loads((DATA_DIR / "fad_reference.json").read_text())


@lru_cache
def allergen_map() -> dict[str, dict]:
    return {
        r["ingredient_id"]: {
            "display_name": r["display_name"],
            "allergens": [a for a in r["allergens"].split("|") if a],
        }
        for r in _csv("allergen_map.csv")
    }


@lru_cache
def process_map() -> dict[str, list[str]]:
    return {r["process_step"]: r["required_any"].split("|") for r in _csv("process_map.csv")}


@lru_cache
def equipment_catalog() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in _csv("equipment_catalog.csv"):
        out.setdefault(r["capability"], []).append(
            {"option": r["option"], "lead_time_days": int(r["lead_time_days"]), "kind": r["kind"]}
        )
    return out


@lru_cache
def rules() -> list[dict]:
    return [{**r, "verified": r["verified"].lower() == "true"} for r in _csv("rules.csv")]
