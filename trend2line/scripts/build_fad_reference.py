"""Compute the half-life reference table from real Wikimedia pageviews.

Usage: python -m scripts.build_fad_reference   (run from the repo root, needs internet)
Edit FADS to taste. Titles that 404 or never decay below 50% of peak are skipped and reported.
"""
import datetime as dt
import json
import os
import statistics

from app.config import DATA_DIR
from app.stages.trend import fetch_pageviews, rolling_mean

UA = os.environ.get("WIKI_USER_AGENT", "Trend2Line/0.1 (set WIKI_USER_AGENT with a contact)")
FADS = [  # candidate article titles; verify each exists on en.wikipedia before relying on it
    "Dalgona coffee", "Cronut", "Unicorn Frappuccino", "Pancake cereal", "Baked feta pasta",
    "Cloud bread", "Rainbow bagel", "Charcoal ice cream", "Sushi burrito", "Dubai chocolate",
    "Hot cocoa bomb", "Butter board", "Tanghulu", "Birria", "Whipped coffee", "Sourdough",
    "Spam musubi", "Raindrop cake", "Freakshake", "Bubble tea",
]
START, END = dt.date(2015, 7, 1), dt.date.today() - dt.timedelta(days=2)
FLASH_RISE_DAYS_MAX = 21


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def main() -> None:
    rows, skipped = [], []
    for title in FADS:
        series = fetch_pageviews(title, START, END, UA)
        if len(series) < 180:
            skipped.append({"title": title, "reason": "missing or too short"})
            continue
        dates = [d for d, _ in series]
        sm = rolling_mean([float(v) for _, v in series], 7)
        pk = max(range(len(sm)), key=sm.__getitem__)
        i = pk
        while i > 0 and sm[i] > 0.1 * sm[pk]:
            i -= 1
        rise = (dates[pk] - dates[i]).days
        half = next(((dates[j] - dates[pk]).days for j in range(pk + 1, len(sm)) if sm[j] < 0.5 * sm[pk]), None)
        if half is None:
            skipped.append({"title": title, "reason": "never fell below 50% of peak (sustained or still live)"})
            continue
        rows.append({"title": title, "peak_date": dates[pk].isoformat(), "rise_days": rise, "half_life_days": half,
                     "class": "flash" if rise <= FLASH_RISE_DAYS_MAX else "standard"})

    classes = {}
    for cls in ("flash", "standard"):
        hl = [r["half_life_days"] for r in rows if r["class"] == cls]
        if len(hl) < 3:
            raise SystemExit(f"Only {len(hl)} '{cls}' fads; add more titles to FADS before trusting this table.")
        classes[cls] = {"half_life_days": {"p25": pct(hl, .25), "median": round(statistics.median(hl), 1),
                                           "p75": pct(hl, .75)}, "n": len(hl)}
    out = {"status": "computed", "computed_on": dt.date.today().isoformat(),
           "method": "7-day smoothed Wikimedia pageviews; half-life = days from peak to first day below 50% of peak",
           "flash_rise_days_max": FLASH_RISE_DAYS_MAX, "classes": classes, "fads": rows, "skipped": skipped}
    (DATA_DIR / "fad_reference.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(classes, indent=2), f"\nskipped: {len(skipped)}")


if __name__ == "__main__":
    main()
