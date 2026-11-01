"""Run the whole verification on a local video. Owner: B (C uses it for the eval).

  python scripts/verify_clip.py --video clips/honest_civic_01.mp4 --code K7Q2XM --listing samples/listing.json
  python scripts/verify_clip.py --video clips/x.mp4 --code K7Q2XM --listing-text "2015 Honda Civic LX, 84k miles, $9,400"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tirekick import verify  # noqa: E402
from tirekick.models import Deal, DealStatus, Listing, ProofChallenge, utcnow  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--code", required=True, help="the 6-char challenge code shown in the video")
    ap.add_argument("--listing", help="path to a Listing JSON file")
    ap.add_argument("--listing-text", help="raw listing text (parsed with Muse Spark)")
    ap.add_argument("--deal-id", default="DEAL-0000")
    ap.add_argument("--out", help="write the full report JSON here")
    args = ap.parse_args()

    if args.listing:
        listing = Listing.model_validate_json(Path(args.listing).read_text(encoding="utf-8"))
    elif args.listing_text:
        listing = verify.parse_listing(text=args.listing_text, listing_id=args.deal_id)
    else:
        sys.exit("give --listing or --listing-text")

    now = utcnow()
    challenge = ProofChallenge(challenge_id="CH-cli", deal_id=args.deal_id, code=args.code.upper(),
                               issued_at=now, expires_at=now + timedelta(hours=24), message_text="")
    deal = Deal(deal_id=args.deal_id, buyer_wa_id="cli", status=DealStatus.PROOF_RECEIVED,
                listing=listing, challenge=challenge)
    report = verify.run_verification(deal, args.video)

    print(f"\nVERDICT: {report.verdict.value.upper()}   fair {report.fair_price_low}-{report.fair_price_high}")
    for e in report.evidence:
        t = f"@{e.clip_start_s:g}s" if e.clip_start_s is not None else ""
        print(f"  {e.id} [{e.severity.value:6}] {e.type.value:22} {t:8} {e.summary}")
    if report.analysis:
        print(f"\nruns={report.analysis.runs} agreement={report.analysis.agreement} notes={report.analysis.model_notes!r}")
    if args.out:
        Path(args.out).write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(f"report written to {args.out}")
    else:
        print(json.dumps({"verdict": report.verdict.value, "evidence": [e.type.value for e in report.evidence]}))


if __name__ == "__main__":
    main()
