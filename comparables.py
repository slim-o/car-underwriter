from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


Platform = Literal["FACEBOOK_MARKETPLACE", "AUTOTRADER", "OTHER"]
Status = Literal[
    "ACTIVE",
    "PRICE_REDUCED",
    "MARKED_SOLD_PRICE_UNKNOWN",
    "REMOVED_OUTCOME_UNKNOWN",
    "SALE_PRICE_CONFIRMED",
]


@dataclass
class Comparable:
    platform: Platform
    url: str
    title: str | None = None
    year: int | None = None
    mileage: int | None = None
    cat: str | None = None
    location: str | None = None
    seller_type: str | None = None
    status: Status = "ACTIVE"
    first_seen: str | None = None
    last_checked: str | None = None
    asking_price_gbp: float | None = None
    transaction_price_gbp: float | None = None
    notes: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_comparables(case_dir: Path) -> list[Comparable]:
    path = case_dir / "comparables.json"
    if not path.exists():
        return []
    data = __import__("json").loads(path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    result = []
    for raw in items:
        result.append(Comparable(**raw))
    return result


def save_comparables(case_dir: Path, items: list[Comparable]) -> None:
    path = case_dir / "comparables.json"
    payload = {
        "saved_at": utc_now(),
        "items": [asdict(item) for item in items],
    }
    path.write_text(
        __import__("json").dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)
    values = sorted(values)
    k = (len(values) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    d0 = values[f] * (c - k)
    d1 = values[c] * (k - f)
    return d0 + d1


def compute_exit_tiers(
    comps: list[Comparable],
    *,
    negotiation_discount: float = 0.06,
    quick_sale_extra_discount: float = 0.08,
) -> dict:
    active_prices = [
        c.asking_price_gbp
        for c in comps
        if c.asking_price_gbp
        and c.status in {"ACTIVE", "PRICE_REDUCED"}
    ]

    confirmed_sales = [
        c.transaction_price_gbp
        for c in comps
        if c.transaction_price_gbp and c.status == "SALE_PRICE_CONFIRMED"
    ]

    evidence_prices = confirmed_sales or active_prices
    evidence_kind = "SALE_PRICE_CONFIRMED" if confirmed_sales else "ASKING_ACTIVE"

    if not evidence_prices:
        return {
            "confidence": "LOW",
            "evidence_kind": evidence_kind,
            "sample_size": 0,
            "advert_price": None,
            "underwritten_sale_price": None,
            "quick_sale_price": None,
        }

    sample_size = len(evidence_prices)
    confidence = "HIGH" if sample_size >= 10 else "MEDIUM" if sample_size >= 6 else "LOW"

    p75 = percentile(evidence_prices, 75)
    p50 = percentile(evidence_prices, 50)
    p25 = percentile(evidence_prices, 25)
    p10 = percentile(evidence_prices, 10)

    def discount(value: float | None, rate: float) -> float | None:
        if value is None:
            return None
        return round(float(value) * (1 - rate), 2)

    worst_case = discount(
        p10,
        min(0.95, negotiation_discount + quick_sale_extra_discount),
    )
    base_case = discount(p50, negotiation_discount)
    best_case = round(float(p75), 2) if p75 is not None else None

    return {
        "confidence": confidence,
        "evidence_kind": evidence_kind,
        "sample_size": sample_size,
        # Legacy keys (kept for compatibility)
        "advert_price": round(float(p50), 2) if p50 is not None else None,
        "underwritten_sale_price": discount(p25, negotiation_discount),
        "quick_sale_price": worst_case,
        # Preferred display keys
        "best_case_price": best_case,
        "base_case_price": base_case,
        "worst_case_price": worst_case,
        "evidence_price_min": round(float(min(evidence_prices)), 2),
        "evidence_price_max": round(float(max(evidence_prices)), 2),
        "assumptions": {
            "negotiation_discount": negotiation_discount,
            "quick_sale_extra_discount": quick_sale_extra_discount,
        },
    }
