"""NHTSA recalls by year/make/model. MODEL-level, not VIN-level (see SPEC honesty note). Owner: B."""

from __future__ import annotations

import json
import re

import httpx

from tirekick.config import data_path
from tirekick.models import Recall
from tirekick.verify.http import get_json

RECALLS_URL = "https://api.nhtsa.gov/recalls/recallsByVehicle"


def parse_recalls(payload: dict) -> list[Recall]:
    out: list[Recall] = []
    for r in payload.get("results") or []:
        out.append(
            Recall(
                campaign_number=str(r.get("NHTSACampaignNumber", "")),
                component=r.get("Component", "") or "",
                summary=r.get("Summary", "") or "",
                consequence=r.get("Consequence", "") or "",
                remedy=r.get("Remedy", "") or "",
                report_date=r.get("ReportReceivedDate"),
            )
        )
    return out


# vPIC names some sub-brands differently from the Recalls API. vPIC decodes a Scion as make "Toyota",
# model "Scion tC"; the Recalls API only knows make "Scion", model "tC" (and 400s otherwise).
SUB_BRANDS = ("Scion",)


def nhtsa_make_model(make: str, model: str) -> tuple[str, str]:
    """Map a vPIC / listing (make, model) to what the NHTSA Recalls API accepts."""
    mk, md = (make or "").strip(), (model or "").strip()
    for brand in SUB_BRANDS:
        if md.lower().startswith(brand.lower() + " "):
            return brand, md[len(brand):].strip()
        if mk.lower() == brand.lower():
            return brand, md
    return mk, md


def lookup_recalls(make: str, model: str, year: int, timeout: float = 10.0) -> list[Recall]:
    make, model = nhtsa_make_model(make, model)
    key = re.sub(r"[^a-z0-9]+", "_", f"{make}_{model}_{year}".lower())
    cache = data_path("cache", "recalls", f"{key}.json")
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
    else:
        try:
            payload = get_json(RECALLS_URL, params={"make": make, "model": model, "modelYear": year},
                               timeout=timeout)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):   # NHTSA answers 400 for unknown make/model
                return []
            raise
        cache.write_text(json.dumps(payload), encoding="utf-8")
    return parse_recalls(payload)
