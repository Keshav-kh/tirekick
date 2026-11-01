"""VIN check digit (pure) and NHTSA vPIC decode (network). Owner: B."""

from __future__ import annotations

import json
import re

import httpx

from tirekick.config import data_path
from tirekick.models import VinDecode

_TRANSLIT = {
    **{str(d): d for d in range(10)},
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}
_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)
_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")  # no I, O, Q

VPIC_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"


def normalize_vin(vin: str) -> str:
    return re.sub(r"[\s\-]", "", vin or "").upper()


def is_north_american(vin: str) -> bool:
    """WMI first character 1-5 = North America; check digit is only mandatory there."""
    v = normalize_vin(vin)
    return bool(v) and v[0] in "12345"


def validate_vin(vin: str) -> tuple[bool, str]:
    """Return (check_digit_valid, normalized_vin). Pure function, no network."""
    v = normalize_vin(vin)
    if not _VIN_RE.match(v):
        return False, v
    total = sum(_TRANSLIT[c] * w for c, w in zip(v, _WEIGHTS))
    remainder = total % 11
    expected = "X" if remainder == 10 else str(remainder)
    return v[8] == expected, v


def _engine_text(row: dict) -> str | None:
    disp = (row.get("DisplacementL") or "").strip()
    cyl = (row.get("EngineCylinders") or "").strip()
    if not disp and not cyl:
        return None
    parts = []
    if disp:
        try:
            parts.append(f"{float(disp):.1f}L")
        except ValueError:
            parts.append(f"{disp}L")
    if cyl:
        parts.append(f"{cyl}cyl")
    return " ".join(parts)


def parse_vpic_row(vin: str, row: dict) -> VinDecode:
    valid, norm = validate_vin(vin)
    year_raw = (row.get("ModelYear") or "").strip()
    error_text = (row.get("ErrorText") or "").strip()
    # vPIC uses ErrorCode "0" for a clean decode
    if (row.get("ErrorCode") or "").strip() == "0":
        error_text = ""
    return VinDecode(
        vin=norm,
        check_digit_valid=valid,
        north_american=is_north_american(norm),
        year=int(year_raw) if year_raw.isdigit() else None,
        make=(row.get("Make") or "").strip().title() or None,
        model=(row.get("Model") or "").strip() or None,
        trim=(row.get("Trim") or "").strip() or None,
        engine=_engine_text(row),
        body=(row.get("BodyClass") or "").strip() or None,
        error_text=error_text,
    )


def decode_vin(vin: str, timeout: float = 10.0) -> VinDecode:
    """NHTSA vPIC decode with an on-disk cache (data/cache/vpic/{vin}.json)."""
    _, norm = validate_vin(vin)
    cache = data_path("cache", "vpic", f"{norm}.json")
    if cache.exists():
        row = json.loads(cache.read_text(encoding="utf-8"))
    else:
        resp = httpx.get(VPIC_URL.format(vin=norm), timeout=timeout)
        resp.raise_for_status()
        results = resp.json().get("Results") or [{}]
        row = results[0]
        cache.write_text(json.dumps(row), encoding="utf-8")
    return parse_vpic_row(norm, row)
