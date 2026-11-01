"""Shared helpers for the eval scripts. Owner: C."""

from __future__ import annotations

import csv
import statistics
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tirekick.models import Deal, DealStatus, Listing, ProofChallenge, utcnow  # noqa: E402

OUT = ROOT / "eval" / "out"


def read_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "0/0"


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def deal_for_clip(listing_json: str, code: str, deal_id: str = "DEAL-0000") -> Deal:
    listing = Listing.model_validate_json(Path(listing_json).read_text(encoding="utf-8"))
    now = utcnow()
    challenge = ProofChallenge(challenge_id="CH-eval", deal_id=deal_id, code=code.upper(),
                               issued_at=now, expires_at=now + timedelta(hours=24), message_text="")
    return Deal(deal_id=deal_id, buyer_wa_id="eval", status=DealStatus.PROOF_RECEIVED,
                listing=listing, challenge=challenge)
