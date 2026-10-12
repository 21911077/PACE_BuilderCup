"""ADK wrapper (day-2 task, UNTESTED here): exposes the pipeline as a tool so the team can use
`adk web` for traces and later split stages into ADK sub-agents.

Check the import path and Agent signature against the google-adk version you install.
Run from adk_app/:  adk web   (needs GEMINI_MODEL and GOOGLE_API_KEY in the environment)
"""
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from google.adk.agents import Agent  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.llm import LLM  # noqa: E402
from app.mock import MOCK_HANDLERS  # noqa: E402
from app import pipeline  # noqa: E402


def assess_trend(trend: str, sku_id: str = "CLASSIC-100", as_of: str = "", market: str = "IN") -> dict:
    """Assess whether our factory can launch a product for a viral food trend.

    Args:
        trend: Trend name, e.g. "Dubai chocolate".
        sku_id: Our existing SKU to compare against.
        as_of: Run date YYYY-MM-DD (defaults to today).
        market: Labelling market code, e.g. "IN".
    """
    s = get_settings()
    day = dt.date.fromisoformat(as_of) if as_of else dt.date.today()
    r = pipeline.run(trend, sku_id, day, market, None, LLM(s, MOCK_HANDLERS), s)
    return {"decision": r["decision"], "blast_radius": r["allergen_blast_radius"],
            "plan": r["plan"], "trust": r["verification"]["trust"]}


root_agent = Agent(
    name="trend2line",
    model=os.environ.get("GEMINI_MODEL", ""),
    description="Turns a viral food trend into a verified factory go/no-go.",
    instruction=("Call assess_trend for the user's trend. Report the verdict, the allergen blast radius and the "
                 "verified plan. Never state numbers that are not in the tool output."),
    tools=[assess_trend],
)
