"""price_comps: comparable prices via Muse Spark web search, with citations. Owner: B.

Muse Spark (Responses API, built-in `web_search` tool) is asked for 3-8 comparable private-party
prices: same year/make/model (trim if possible), similar mileage, near the listing's location,
each with its source URL. Code then decides what counts:
- a comp must carry an http(s) URL; when the response has url_citation annotations, the URL's
  host must be one the model actually cited (no invented sources)
- the price must be in the listing's currency and plausible (35%-250% of the asking price)
- one price per URL
low / median / high are computed here from the surviving numbers, never taken from the model.
If the JSON is unusable, the fallback reads one price out of each cited passage.

Cache: data/cache/comps/{sha1(year|make|model|trim|location)}.json (only non-empty results).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import statistics
import time
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError

from tirekick.config import data_path
from tirekick.models import Listing, PriceComps
from tirekick.verify import muse

log = logging.getLogger(__name__)

MIN_RATIO, MAX_RATIO = 0.35, 2.5
MAX_COMPS = 8
CACHE_VERSION = 1

COMPS_INSTRUCTIONS = (
    "You find comparable used-car prices on the web for a private buyer. Use web search. Report only "
    "prices you saw on a specific page (a listing, a sold listing, or a private-party valuation page) and "
    "give that page's URL. Never estimate or average; never invent a URL. Reply with JSON only."
)
COMPS_PROMPT = """Find 3 to 8 comparable private-party prices for this car:
  {year} {make} {model}{trim}{mileage}
  near {location}; prices in {currency}.
Prefer the same trim and mileage within about 25%. Include each price exactly as listed.

Reply with JSON only, no prose, in exactly this shape:
{{"comps": [{{"price": 9200, "currency": "{currency}", "url": "https://...", "title": "page title",
  "year": 2015, "mileage": 81000, "location": "city"}}]}}"""


class CompItem(BaseModel):
    price: int | float | str | None = None
    currency: str | None = None
    url: str | None = None
    title: str = ""
    year: int | None = None
    mileage: int | float | str | None = None
    location: str | None = None


class CompsOut(BaseModel):
    comps: list[CompItem] = Field(default_factory=list)


# --------------------------------------------------------------------------- helpers


def cache_key(listing: Listing) -> str:
    parts = [str(listing.year or ""), listing.make or "", listing.model or "", listing.trim or "",
             listing.location or ""]
    canon = "|".join(re.sub(r"\s+", " ", p.strip().lower()) for p in parts)
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()[:20]


def _host(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def _valid_url(url: str | None) -> bool:
    if not url:
        return False
    p = urlparse(url.strip())
    return p.scheme in ("http", "https") and bool(p.hostname) and "." in (p.hostname or "")


def _price(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(value))
    m = re.search(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k\b)?", str(value), re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return int(round(v * 1000 if m.group(2) else v))


def _currency_ok(cur: str | None, want: str) -> bool:
    if not cur:
        return True
    c = cur.strip().upper()
    aliases = {"$": "USD", "US$": "USD", "DHS": "AED", "DH": "AED", "DIRHAM": "AED", "DIRHAMS": "AED"}
    return aliases.get(c, c) == want.upper()


def summarize(prices: list[int]) -> tuple[int | None, int | None, int | None]:
    """(low, median, high) in code. With 5+ prices the single lowest and highest are trimmed off
    low/high so one outlier can't drag the opening offer down; the median uses every price."""
    if not prices:
        return None, None, None
    s = sorted(prices)
    med = int(statistics.median(s))
    band = s[1:-1] if len(s) >= 5 else s
    return band[0], med, band[-1]


def select_comps(items: list[CompItem], listing: Listing, cited_hosts: set[str]) -> tuple[list[tuple[int, str]], dict]:
    """Apply the code-side rules. Returns ([(price, url)], drop counts)."""
    ask = listing.asking_price
    lo, hi = ask * MIN_RATIO, ask * MAX_RATIO
    kept: list[tuple[int, str]] = []
    seen_urls: set[str] = set()
    dropped = {"no_url": 0, "uncited": 0, "currency": 0, "implausible": 0, "duplicate": 0}
    for it in items:
        url = (it.url or "").strip()
        if not _valid_url(url):
            dropped["no_url"] += 1
            continue
        if cited_hosts and _host(url) not in cited_hosts:
            dropped["uncited"] += 1
            continue
        if not _currency_ok(it.currency, listing.currency):
            dropped["currency"] += 1
            continue
        price = _price(it.price)
        if price is None or not lo <= price <= hi:
            dropped["implausible"] += 1
            continue
        key = url.rstrip("/").lower()
        if key in seen_urls:
            dropped["duplicate"] += 1
            continue
        seen_urls.add(key)
        kept.append((price, url))
        if len(kept) >= MAX_COMPS:
            break
    return kept, dropped


def items_from_citations(result: muse.SearchResult) -> list[CompItem]:
    """Fallback: one price from each cited passage (text[start:end]) with that citation's URL."""
    out: list[CompItem] = []
    for c in result.citations:
        if c.start_index is None or c.end_index is None:
            continue
        passage = result.text[max(0, c.start_index):c.end_index]
        m = re.search(r"(?:\$|USD\s?|AED\s?)\s?(\d{1,3}(?:,\d{3})+|\d{3,6})", passage, re.I)
        if m:
            cur = "AED" if "AED" in m.group(0).upper() else "USD"
            out.append(CompItem(price=m.group(1), currency=cur, url=c.url, title=c.title))
    return out


def _parse_items(result: muse.SearchResult) -> list[CompItem]:
    try:
        return CompsOut.model_validate_json(muse.extract_json(result.text)).comps
    except (ValidationError, ValueError):
        try:  # a bare list is fine too
            return [CompItem(**x) for x in json.loads(muse.extract_json(result.text)) if isinstance(x, dict)]
        except (ValueError, TypeError, ValidationError):
            return []


# --------------------------------------------------------------------------- public


def comps_from_result(result: muse.SearchResult, listing: Listing) -> PriceComps:
    if not result.searched:
        return PriceComps(currency=listing.currency, note="Muse Spark answered without running a web search; "
                          "no comps used.")
    cited_hosts = {_host(c.url) for c in result.citations if _valid_url(c.url)}
    items = _parse_items(result)
    source = "json"
    if not items:
        items, source = items_from_citations(result), "citations"
    kept, dropped = select_comps(items, listing, cited_hosts)
    low, med, high = summarize([p for p, _ in kept])
    dropped_txt = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in dropped.items() if v)
    note = (f"{len(kept)} cited private-party prices from web search ({source})"
            + (f"; dropped {dropped_txt}" if dropped_txt else "") + ".")
    return PriceComps(currency=listing.currency, low=low, median=med, high=high, n=len(kept),
                      sources=[u for _, u in kept], note=note)


def price_comps(listing: Listing) -> PriceComps:
    """Never raises: any failure returns PriceComps(n=0, note=why)."""
    if not (listing.year and listing.make and listing.model):
        return PriceComps(currency=listing.currency, note="Need the year, make and model to look up comps.")
    cache = data_path("cache", "comps", f"{cache_key(listing)}.json")
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if cached.get("version") == CACHE_VERSION:
                return PriceComps.model_validate(cached["comps"])
        except (ValueError, KeyError, ValidationError):
            log.warning("ignoring unreadable comps cache %s", cache)
    if not muse.available():
        return PriceComps(currency=listing.currency, note="Comps unavailable: no Meta Model API key configured.")

    mileage = f", about {listing.mileage:,} {listing.mileage_unit}" if listing.mileage else ""
    prompt = COMPS_PROMPT.format(
        year=listing.year, make=listing.make, model=listing.model,
        trim=f" {listing.trim}" if listing.trim else "", mileage=mileage,
        location=listing.location or ("the UAE" if listing.currency == "AED" else "the United States"),
        currency=listing.currency,
    )
    try:
        result = muse.web_search(prompt, instructions=COMPS_INSTRUCTIONS, tag="comps")
    except Exception as e:  # noqa: BLE001 - comps are optional; the report works without them
        log.warning("comps web search failed: %s", e)
        return PriceComps(currency=listing.currency, note=f"Comps unavailable: web search failed ({type(e).__name__}).")
    comps = comps_from_result(result, listing)
    if comps.n > 0:
        cache.write_text(json.dumps({"version": CACHE_VERSION, "fetched_at": int(time.time()),
                                     "comps": comps.model_dump(), "raw_text": result.text,
                                     "citations": [c.__dict__ for c in result.citations]}, indent=2),
                         encoding="utf-8")
    return comps
