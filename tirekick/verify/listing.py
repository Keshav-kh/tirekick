"""parse_listing: Muse Spark reads pasted listing text and/or screenshots. Owner: B.

Never fetch or scrape the URL; we only store it. The buyer pastes the text or screenshots.

The model extracts fields; code then checks them: the VIN must be 17 valid VIN characters, and
for text-only input the asking price must be a price that actually appears in the text. If the
model call fails, a deterministic regex parser reads the text instead, so the only exception the
caller sees is the contract's ValueError ("no asking price found").
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Literal

from pydantic import BaseModel

from tirekick.models import Listing
from tirekick.verify import prompts
from tirekick.verify.muse import image_part, muse_json, text_part
from tirekick.verify.vin import _VIN_RE, normalize_vin

log = logging.getLogger(__name__)


class ListingExtract(BaseModel):
    title: str = ""
    asking_price: int | None = None
    currency: str = "USD"
    year: int | None = None
    make: str | None = None
    model: str | None = None
    trim: str | None = None
    engine: str | None = None
    mileage: int | None = None
    mileage_unit: Literal["mi", "km"] = "mi"
    vin: str | None = None
    location: str | None = None
    seller_name: str | None = None
    description: str = ""


def _source_from_url(url: str | None) -> str:
    u = (url or "").lower()
    if "facebook.com" in u or "fb.com" in u:
        return "facebook_marketplace"
    if "dubizzle" in u:
        return "dubizzle"
    return "other"


# --------------------------------------------------------------------------- deterministic helpers

_NUM = r"(\d{1,3}(?:[,.]\d{3})+|\d+(?:\.\d+)?)"
PRICE_PATTERNS = [
    (re.compile(r"\$\s?" + _NUM + r"(\s?k\b)?", re.I), "USD"),
    (re.compile(r"\b(?:usd)\s?" + _NUM + r"(\s?k\b)?", re.I), "USD"),
    (re.compile(_NUM + r"(\s?k)?\s?(?:usd|dollars)\b", re.I), "USD"),
    (re.compile(r"\b(?:aed|dhs?\.?)\s?" + _NUM + r"(\s?k\b)?", re.I), "AED"),
    (re.compile(_NUM + r"(\s?k)?\s?(?:aed|dhs?|dirhams?)\b", re.I), "AED"),
    (re.compile(r"\b(?:price|asking)\s*[:\-]?\s*" + _NUM + r"(\s?k\b)?", re.I), None),
]
MILEAGE = re.compile(_NUM + r"\s?(k)?\s?(miles|mi|kms?|kilometers|kilometres)\b", re.I)
YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
MAKES = ["Acura", "Audi", "BMW", "Buick", "Cadillac", "Chevrolet", "Chevy", "Chrysler", "Dodge", "Ford", "GMC",
         "Genesis", "Honda", "Hyundai", "Infiniti", "Jaguar", "Jeep", "Kia", "Land Rover", "Lexus", "Lincoln",
         "Mazda", "Mercedes-Benz", "Mercedes", "Mini", "Mitsubishi", "Nissan", "Porsche", "Ram", "Subaru",
         "Tesla", "Toyota", "Volkswagen", "VW", "Volvo"]
_MAKE_RE = re.compile(r"\b(" + "|".join(re.escape(m) for m in MAKES) + r")\b\s+([A-Za-z0-9\-]+)(?:\s+([A-Z0-9][A-Za-z0-9\-]{0,5}))?", re.I)


def _to_int(num: str, k: str | None) -> int | None:
    raw = num.replace(",", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):   # "15.000" = 15000 (European thousands)
        raw = raw.replace(".", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    if k and k.strip():
        value *= 1000
    return int(round(value))


def prices_in_text(text: str) -> list[tuple[int, str | None]]:
    """Every money figure in the text as (amount, currency or None), in order of appearance."""
    hits: list[tuple[int, int, str | None]] = []
    for regex, cur in PRICE_PATTERNS:
        for m in regex.finditer(text or ""):
            value = _to_int(m.group(1), m.group(2))
            if value is not None and value >= 100:
                hits.append((m.start(), value, cur))
    seen, out = set(), []
    for _, value, cur in sorted(hits):
        if value not in seen:
            seen.add(value)
            out.append((value, cur))
    return out


def find_vin(text: str) -> str | None:
    for token in re.findall(r"\b[A-Za-z0-9]{17}\b", text or ""):
        v = normalize_vin(token)
        if _VIN_RE.match(v) and re.search(r"\d", v) and re.search(r"[A-Z]", v):
            return v
    return None


def clean_vin(vin: str | None) -> str | None:
    v = normalize_vin(vin or "")
    return v if _VIN_RE.match(v) else None


def regex_extract(text: str) -> ListingExtract:
    """Deterministic fallback when the model is unavailable: price, year, make/model/trim, mileage, VIN."""
    prices = prices_in_text(text)
    year = YEAR.search(text or "")
    mm = _MAKE_RE.search(text or "")
    miles = MILEAGE.search(text or "")
    unit = "km" if miles and miles.group(3).lower().startswith("k") else "mi"
    trim = mm.group(3) if mm and mm.group(3) and not mm.group(3).isdigit() else None
    title = (text or "").strip().splitlines()[0][:120] if (text or "").strip() else ""
    return ListingExtract(
        title=title,
        asking_price=prices[0][0] if prices else None,
        currency=(prices[0][1] or "USD") if prices else "USD",
        year=int(year.group(1)) if year else None,
        make=mm.group(1).title() if mm else None, model=mm.group(2).title() if mm else None, trim=trim,
        mileage=_to_int(miles.group(1), miles.group(2)) if miles else None, mileage_unit=unit,
        vin=find_vin(text), description=(text or "")[:2000],
    )


# --------------------------------------------------------------------------- public


def parse_listing(text: str | None = None, image_paths: list[str] | None = None,
                  url: str | None = None, listing_id: str | None = None) -> Listing:
    if not text and not image_paths:
        raise ValueError("parse_listing needs listing text or at least one screenshot")
    parts: list[dict] = [text_part("Extract the listing fields as JSON. asking_price is the seller's asking "
                                   "price as a whole number (no symbols or commas); currency is a 3-letter code.")]
    if text:
        parts.append(text_part(f"Listing text:\n{text}"))
    for p in image_paths or []:
        parts.append(image_part(p))
    try:
        extract = muse_json(
            [{"role": "system", "content": prompts.LISTING_SYSTEM}, {"role": "user", "content": parts}],
            ListingExtract, tag="listing",
        )
    except Exception as e:  # noqa: BLE001 - model down: read the text deterministically instead
        log.warning("listing model call failed, using the regex parser: %s", e)
        if not text:
            raise ValueError("couldn't read the screenshots right now; please paste the listing text") from e
        extract = regex_extract(text)

    # Code checks the model's facts.
    if text and not image_paths and extract.asking_price is not None:
        in_text = [v for v, _ in prices_in_text(text)]
        if in_text and extract.asking_price not in in_text:
            log.warning("model price %s not in listing text %s; using the text's first price",
                        extract.asking_price, in_text)
            extract.asking_price = in_text[0]
    if extract.asking_price is None or extract.asking_price <= 0:
        raise ValueError("No asking price found in the listing")
    data = extract.model_dump()
    data.update(
        vin=clean_vin(extract.vin) or (find_vin(text) if text else None),
        currency=(extract.currency or "USD").strip().upper()[:3] or "USD",
        listing_id=listing_id or f"L-{uuid.uuid4().hex[:8]}",
        source=_source_from_url(url), url=url, raw_text=text or "",
    )
    return Listing(**data)
