"""NHTSA recalls by year/make/model. MODEL-level, not VIN-level (see SPEC honesty note). Owner: B."""

from __future__ import annotations

import json
import re

import httpx

from tirekick.config import data_path
from tirekick.models import Recall

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


def lookup_recalls(make: str, model: str, year: int, timeout: float = 10.0) -> list[Recall]:
    key = re.sub(r"[^a-z0-9]+", "_", f"{make}_{model}_{year}".lower())
    cache = data_path("cache", "recalls", f"{key}.json")
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
    else:
        resp = httpx.get(
            RECALLS_URL,
            params={"make": make, "model": model, "modelYear": year},
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        cache.write_text(json.dumps(payload), encoding="utf-8")
    return parse_recalls(payload)
