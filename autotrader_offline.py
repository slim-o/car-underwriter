from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class AutoTraderListing:
    url: str
    title: str | None
    price_gbp: float | None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip().replace(",", "")
        s = re.sub(r"[^0-9.]", "", s)
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def _iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_dicts(item)


def _extract_from_jsonld(doc: Any, base_url: str) -> list[AutoTraderListing]:
    listings: list[AutoTraderListing] = []

    for item in _iter_dicts(doc):
        t = item.get("@type")
        if t not in {"ItemList", "Vehicle", "Car", "Product"}:
            continue

        if t == "ItemList":
            for elem in item.get("itemListElement", []) or []:
                if isinstance(elem, dict) and "item" in elem:
                    elem = elem["item"]
                if not isinstance(elem, dict):
                    continue
                url = elem.get("url") or elem.get("@id")
                if url:
                    url = urljoin(base_url, url)
                title = elem.get("name") or elem.get("title")
                offers = elem.get("offers") or {}
                if isinstance(offers, list) and offers:
                    offers = offers[0]
                price = _safe_float(
                    offers.get("price") if isinstance(offers, dict) else None
                )
                if url and (title or price is not None):
                    listings.append(AutoTraderListing(url=url, title=title, price_gbp=price))
            continue

        url = item.get("url") or item.get("@id")
        if url:
            url = urljoin(base_url, url)
        title = item.get("name") or item.get("title")
        offers = item.get("offers") or {}
        if isinstance(offers, list) and offers:
            offers = offers[0]
        price = _safe_float(offers.get("price") if isinstance(offers, dict) else None)
        if url and (title or price is not None):
            listings.append(AutoTraderListing(url=url, title=title, price_gbp=price))

    # De-dupe by URL
    seen = set()
    unique: list[AutoTraderListing] = []
    for listing in listings:
        if listing.url in seen:
            continue
        seen.add(listing.url)
        unique.append(listing)
    return unique


def extract_listings_from_saved_html(
    html: str,
    *,
    base_url: str = "https://www.autotrader.co.uk",
) -> list[AutoTraderListing]:
    """
    Parses a user-supplied saved HTML file of an Auto Trader search results page.

    This does not fetch URLs or automate access to Auto Trader; it only extracts
    data from an HTML blob you provide (e.g. "Save page as...").
    """
    soup = BeautifulSoup(html or "", "html.parser")

    listings: list[AutoTraderListing] = []

    for script in soup.select("script[type='application/ld+json']"):
        raw = (script.string or "").strip()
        if not raw:
            continue
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            continue
        listings.extend(_extract_from_jsonld(doc, base_url))

    if listings:
        return listings

    # Fallback heuristic: find car-details links and nearby £ prices in text.
    text = soup.get_text("\n", strip=True)
    prices = [
        (m.start(), _safe_float(m.group(1)))
        for m in re.finditer(r"£\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)", text)
    ]

    def nearest_price(pos: int) -> float | None:
        if not prices:
            return None
        best = min(prices, key=lambda x: abs(x[0] - pos))
        return best[1]

    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if "/car-details/" not in href:
            continue
        url = urljoin(base_url, href)
        title = a.get_text(" ", strip=True) or None
        price = nearest_price(text.find(title)) if title else None
        listings.append(AutoTraderListing(url=url, title=title, price_gbp=price))

    # De-dupe by URL
    seen = set()
    unique: list[AutoTraderListing] = []
    for listing in listings:
        if listing.url in seen:
            continue
        seen.add(listing.url)
        unique.append(listing)
    return unique

