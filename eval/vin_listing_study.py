"""C2: the 100-listing VIN study. Owner: C.

  python eval/vin_listing_study.py eval/data/listings.csv

Hand-collected listings only (no scraping). Uses the REAL NHTSA APIs; unset TIREKICK_FAKE_AI.
Writes eval/out/listings_scored.csv and prints the RESULTS.md numbers.
"""

from __future__ import annotations

import os
import sys

from _common import OUT, pct, read_rows, write_rows

from tirekick.verify.recalls import lookup_recalls
from tirekick.verify.report_builder import _loosely_equal
from tirekick.verify.vin import decode_vin, is_north_american, validate_vin


def main(path: str) -> None:
    if os.getenv("TIREKICK_FAKE_AI") == "1":
        sys.exit("unset TIREKICK_FAKE_AI: this study must use the real NHTSA APIs")
    rows = read_rows(path)
    scored = []
    for r in rows:
        valid, vin = validate_vin(r["vin"])
        na = is_north_american(vin)
        out = {**r, "vin_norm": vin, "north_american": na, "check_digit_valid": valid,
               "decoded_year": "", "decoded_make": "", "decoded_model": "", "decoded_trim": "",
               "core_mismatch": "", "trim_mismatch": "", "recalls_for_model": "", "error": ""}
        try:
            d = decode_vin(vin)
            out.update(decoded_year=d.year or "", decoded_make=d.make or "", decoded_model=d.model or "",
                       decoded_trim=d.trim or "")
            year = int(r["year"]) if (r.get("year") or "").isdigit() else None
            core = bool((year and d.year and year != d.year)
                        or (r.get("make") and d.make and not _loosely_equal(r["make"], d.make))
                        or (r.get("model") and d.model and not _loosely_equal(r["model"], d.model)))
            out["core_mismatch"] = core
            out["trim_mismatch"] = bool(not core and r.get("trim") and d.trim and not _loosely_equal(r["trim"], d.trim))
            if d.make and d.model and d.year:
                out["recalls_for_model"] = len(lookup_recalls(d.make, d.model, d.year))
        except Exception as e:  # noqa: BLE001
            out["error"] = str(e)[:200]
        scored.append(out)
    write_rows(OUT / "listings_scored.csv", scored)

    n = len(scored)
    na_rows = [s for s in scored if s["north_american"]]
    decoded = [s for s in scored if s["core_mismatch"] != ""]
    with_recalls = [s for s in decoded if (s["recalls_for_model"] or 0) > 0]
    unmentioned = [s for s in with_recalls if (s.get("mentions_recall") or "").lower() not in {"y", "yes", "1", "true"}]
    print(f"Listings: {n}  (North-American VINs: {len(na_rows)}, decoded OK: {len(decoded)})")
    print(f"Invalid check digit (NA VINs only): {pct(sum(not s['check_digit_valid'] for s in na_rows), len(na_rows))}")
    print(f"Year/make/model mismatch vs VIN:    {pct(sum(bool(s['core_mismatch']) for s in decoded), len(decoded))}")
    print(f"Trim mismatch vs VIN:               {pct(sum(bool(s['trim_mismatch']) for s in decoded), len(decoded))}")
    print(f"Model has >=1 NHTSA recall:         {pct(len(with_recalls), len(decoded))}")
    print(f"  ...and listing never mentions it: {pct(len(unmentioned), len(with_recalls))}")
    print("Note: recalls are model-level (year/make/model), not VIN-level.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "eval/data/listings.csv")
