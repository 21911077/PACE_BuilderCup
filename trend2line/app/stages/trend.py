"""Trend Scout: Wikipedia pageviews as a public demand proxy. All math is deterministic."""
import datetime as dt
import math
from urllib.parse import quote

import httpx

WIKI_API = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
    "all-access/user/{title}/daily/{start}/{end}"
)
Series = list[tuple[dt.date, int]]


def search_candidates(query: str, user_agent: str, limit: int = 5) -> list[str]:
    r = httpx.get(
        WIKI_API,
        params={"action": "opensearch", "search": query, "limit": limit, "namespace": 0, "format": "json"},
        headers={"User-Agent": user_agent},
        timeout=10,
    )
    r.raise_for_status()
    return list(r.json()[1])


def fetch_pageviews(title: str, start: dt.date, end: dt.date, user_agent: str) -> Series:
    url = PAGEVIEWS.format(
        title=quote(title.replace(" ", "_"), safe=""),
        start=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
    )
    r = httpx.get(url, headers={"User-Agent": user_agent}, timeout=15)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return [
        (dt.datetime.strptime(i["timestamp"][:8], "%Y%m%d").date(), int(i["views"]))
        for i in r.json().get("items", [])
    ]


def synthetic_series(start: dt.date, end: dt.date, peak: dt.date, rise_days: int,
                     half_life: int, peak_views: int = 20000, baseline: int = 40) -> Series:
    """Clearly synthetic curve for MOCK_LLM mode only. Never presented as real data."""
    out, d = [], start
    while d <= end:
        delta = (d - peak).days
        if delta <= 0:
            v = baseline + peak_views * math.exp(-((delta / max(rise_days / 2.5, 1)) ** 2))
        else:
            v = baseline + peak_views * 0.5 ** (delta / half_life)
        out.append((d, int(v)))
        d += dt.timedelta(days=1)
    return out


def rolling_mean(values: list[float], window: int) -> list[float]:
    out, total = [], 0.0
    for i, v in enumerate(values):
        total += v
        if i >= window:
            total -= values[i - window]
        out.append(total / min(i + 1, window))
    return out


def capture_share(days_to_shelf: float, half_life_days: float) -> float:
    """Share of today's interest still left when the product lands: 0.5 ** (T / h)."""
    return round(0.5 ** (days_to_shelf / half_life_days), 3)


def analyze(series: Series, as_of: dt.date, reference: dict, smooth_window: int = 7) -> dict:
    pts = [(d, v) for d, v in series if d <= as_of]
    if len(pts) < 120:
        return {"stage": "insufficient_data", "points": len(pts)}
    dates = [d for d, _ in pts]
    sm = rolling_mean([float(v) for _, v in pts], smooth_window)
    cur = sm[-1]
    peak_i = max(range(len(sm)), key=sm.__getitem__)
    peak, peak_date = sm[peak_i], dates[peak_i]
    prev90 = sm[-91] if len(sm) > 90 else sm[0]
    momentum = min(cur / prev90, 99.0) if prev90 > 0 else 99.0
    days_since_peak = (as_of - peak_date).days

    i = peak_i
    while i > 0 and sm[i] > 0.1 * peak:
        i -= 1
    rise_days = (peak_date - dates[i]).days

    observed_half_life = None
    for j in range(peak_i + 1, len(sm)):
        if sm[j] < 0.5 * peak:
            observed_half_life = (dates[j] - peak_date).days
            break

    if days_since_peak >= 365 and cur >= 0.4 * peak:
        stage = "sustained"
    elif cur < 0.8 * peak and days_since_peak > 14:
        stage = "decaying"
    elif momentum > 1.5:
        stage = "rising"
    else:
        stage = "peaking"

    cls = "flash" if rise_days <= reference["flash_rise_days_max"] else "standard"
    hl = reference["classes"][cls]["half_life_days"]
    weekly = [[dates[k].isoformat(), round(sm[k], 1)] for k in range(0, len(sm), 7)]
    return {
        "stage": stage,
        "momentum_90d": round(momentum, 2),
        "current_views_smoothed": round(cur, 1),
        "peak_views_smoothed": round(peak, 1),
        "peak_date": peak_date.isoformat(),
        "days_since_peak": days_since_peak,
        "rise_days": rise_days,
        "observed_half_life_days": observed_half_life,
        "reference_class": cls,
        "reference_half_life_days": hl,
        "reference_status": reference.get("status", "unknown"),
        "series_weekly": weekly,
    }
