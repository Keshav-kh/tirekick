"""parse_listing: Muse Spark reads pasted listing text and/or screenshots. Owner: B.

Never fetch or scrape the URL; we only store it. The buyer pastes the text or screenshots.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel

from tirekick.models import Listing
from tirekick.verify import prompts
from tirekick.verify.muse import image_part, muse_json, text_part


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


def parse_listing(text: str | None = None, image_paths: list[str] | None = None,
                  url: str | None = None, listing_id: str | None = None) -> Listing:
    if not text and not image_paths:
        raise ValueError("parse_listing needs listing text or at least one screenshot")
    parts: list[dict] = [text_part("Extract the listing fields as JSON.")]
    if text:
        parts.append(text_part(f"Listing text:\n{text}"))
    for p in image_paths or []:
        parts.append(image_part(p))
    extract = muse_json(
        [{"role": "system", "content": prompts.LISTING_SYSTEM}, {"role": "user", "content": parts}],
        ListingExtract, tag="listing",
    )
    if extract.asking_price is None:
        raise ValueError("No asking price found in the listing")
    data = extract.model_dump()
    data.update(
        listing_id=listing_id or f"L-{uuid.uuid4().hex[:8]}",
        source=_source_from_url(url), url=url, raw_text=text or "",
    )
    return Listing(**data)
