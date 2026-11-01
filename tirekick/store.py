"""Deal persistence: one JSON file per deal under data/deals/. Owner: A."""

from __future__ import annotations

import os
import secrets

from tirekick.config import data_path
from tirekick.models import Deal, DealStatus, utcnow

TERMINAL = {DealStatus.AGREED, DealStatus.WALKED_AWAY, DealStatus.EXPIRED}


def _path(deal_id: str):
    return data_path("deals", f"{deal_id}.json")


def save_deal(deal: Deal) -> None:
    deal.updated_at = utcnow()
    path = _path(deal.deal_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(deal.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic: a crash can't leave a half-written deal


def get_deal(deal_id: str) -> Deal | None:
    path = _path(deal_id)
    if not path.exists():
        return None
    return Deal.model_validate_json(path.read_text(encoding="utf-8"))


def all_deals() -> list[Deal]:
    folder = data_path("deals", "x").parent
    deals = [Deal.model_validate_json(p.read_text(encoding="utf-8")) for p in folder.glob("DEAL-*.json")]
    return sorted(deals, key=lambda d: d.updated_at, reverse=True)


def find_deal_by_seller(wa_id: str) -> Deal | None:
    return next((d for d in all_deals() if d.seller_wa_id == wa_id and d.status not in TERMINAL), None)


def find_active_deal_by_buyer(wa_id: str) -> Deal | None:
    return next((d for d in all_deals() if d.buyer_wa_id == wa_id and d.status not in TERMINAL), None)


def new_deal_id() -> str:
    while True:
        deal_id = f"DEAL-{secrets.randbelow(9000) + 1000}"
        if not _path(deal_id).exists():
            return deal_id


def already_processed(message_id: str) -> bool:
    """De-duplicate webhook retries. Returns True if this id was seen before (and records it)."""
    if not message_id:
        return False
    path = data_path("seen_message_ids.txt")
    seen = set(path.read_text(encoding="utf-8").split()) if path.exists() else set()
    if message_id in seen:
        return True
    with path.open("a", encoding="utf-8") as f:
        f.write(message_id + "\n")
    return False
