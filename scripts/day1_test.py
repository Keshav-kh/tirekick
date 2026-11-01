"""Day-1 test (docs/workstream-B-intelligence.md section 0). Owner: B.

  python scripts/day1_test.py --clips eval/data/light_check.csv --runs 3

Reads the labelled clips, runs analyze_proof_take `runs` times per clip (each run is itself a
single sample here so you can see run-to-run agreement), and prints the GO / NO-GO gates.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tirekick.models import LightName, Listing, ProofChallenge, utcnow  # noqa: E402
from tirekick.verify import analyze_proof_take, validate_vin  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", default="eval/data/light_check.csv")
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.clips, encoding="utf-8")))
    if not rows:
        sys.exit(f"no rows in {args.clips}; C labels the clips there first")

    taped_caught = taped_total = false_alarms = honest_total = 0
    vin_ok = vin_total = code_ok = code_total = 0
    slowest = 0.0
    for row in rows:
        listing = Listing(listing_id=row["clip"], asking_price=1, year=int(row["year"] or 0) or None,
                          make=row["make"] or None, model=row["model"] or None)
        now = utcnow()
        code = (row.get("code") or "AAAAAA").upper()
        challenge = ProofChallenge(challenge_id="CH-day1", deal_id="DEAL-0000", code=code,
                                   issued_at=now, expires_at=now + timedelta(hours=1), message_text="")
        masked = (row.get("masked_light") or "none").strip().lower()
        hits = []
        for _ in range(args.runs):
            t0 = time.time()
            a = analyze_proof_take(row["clip"], challenge, listing, runs=1)
            slowest = max(slowest, time.time() - t0)
            status = {o.light.value: o.lit_at_key_on for o in a.lights}
            hits.append(status)
            if row.get("vin"):
                vin_total += 1
                vin_ok += int(bool(a.windshield_vin_read) and validate_vin(a.windshield_vin_read)[0])
            if row.get("code"):
                code_total += 1
                code_ok += int(a.code_matches)
        if masked != "none":
            taped_total += 1
            taped_caught += int(all(h.get(masked) is False for h in hits))
        else:
            honest_total += 1
            false_alarms += int(any(v is False for h in hits for v in h.values()))
        print(f"{row['clip']:40} masked={masked:13} runs={[h.get(LightName.CHECK_ENGINE.value) for h in hits]}")

    print("\nGATES")
    print(f"  Lights : taped caught {taped_caught}/{taped_total} (need all, in all runs); "
          f"honest clips with a false alarm {false_alarms}/{honest_total} (need 0)")
    print(f"  VIN    : {vin_ok}/{vin_total} reads pass the check digit;  code read {code_ok}/{code_total}")
    print(f"  Speed  : slowest run {slowest:.1f}s (need <= 60s)")


if __name__ == "__main__":
    main()
