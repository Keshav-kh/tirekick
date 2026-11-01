"""C4: light check with the product's merged (majority-vote) analysis. Owner: C.

  python eval/light_check_eval.py eval/data/light_check.csv --runs 3

scripts/day1_test.py shows raw run-to-run behaviour; this script measures what the product does.
"""

from __future__ import annotations

import argparse
from datetime import timedelta

from _common import OUT, pct, read_rows, write_rows

from tirekick.models import Listing, ProofChallenge, utcnow
from tirekick.verify import analyze_proof_take


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default="eval/data/light_check.csv")
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    out = []
    for r in read_rows(args.csv):
        listing = Listing(listing_id=r["clip"], asking_price=1,
                          year=int(r["year"]) if (r.get("year") or "").isdigit() else None,
                          make=r.get("make") or None, model=r.get("model") or None)
        now = utcnow()
        ch = ProofChallenge(challenge_id="CH-light", deal_id="DEAL-0000", code=(r.get("code") or "AAAAAA").upper(),
                            issued_at=now, expires_at=now + timedelta(hours=1), message_text="")
        a = analyze_proof_take(r["clip"], ch, listing, runs=args.runs)
        dark = sorted(o.light.value for o in a.lights if o.lit_at_key_on is False)
        masked = (r.get("masked_light") or "none").strip().lower()
        out.append({"clip": r["clip"], "masked_light": masked, "flagged_dark": ";".join(dark),
                    "caught": masked != "none" and masked in dark,
                    "false_alarm": bool([d for d in dark if d != masked]),
                    "agreement": a.agreement, "runs": a.runs})
    write_rows(OUT / "light_check_scored.csv", out)

    taped = [x for x in out if x["masked_light"] != "none"]
    honest = [x for x in out if x["masked_light"] == "none"]
    print(f"Hidden-light catch rate: {pct(sum(x['caught'] for x in taped), len(taped))}")
    print(f"False alarms (any wrong light flagged): {pct(sum(x['false_alarm'] for x in out), len(out))}"
          f"   on honest clips: {pct(sum(x['false_alarm'] for x in honest), len(honest))}")
    if out:
        print(f"Mean run agreement: {sum(x['agreement'] for x in out) / len(out):.2f}")


if __name__ == "__main__":
    main()
