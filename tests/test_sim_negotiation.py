"""Tests for eval/sim_negotiation.py (owner: C). Rule bots only: no network, no model."""

import random
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
import sim_negotiation as sim  # noqa: E402

from tirekick.models import NegotiationStatus  # noqa: E402
from tirekick.negotiate import apply_seller_reply  # noqa: E402


@pytest.fixture(autouse=True)
def _fake(monkeypatch):
    monkeypatch.setenv("TIREKICK_FAKE_AI", "1")


def test_schedule_is_balanced():
    cards = sim.load_cards()
    rows = sim.schedule(cards)
    assert len(rows) == 2 * len(cards)
    per_participant: dict[int, list] = {}
    for i, order, card, cond in rows:
        per_participant.setdefault(i, []).append((card["card_id"], cond))
    for i, pair in per_participant.items():
        assert pair[0][0] != pair[1][0], "each participant must see two different cars"
        assert {c for _, c in pair} == {"H", "T"}
        assert pair[0][1] == ("H" if i % 2 == 0 else "T"), "order alternates"
    by_card = Counter((card["card_id"], cond) for _, _, card, cond in rows)
    assert all(by_card[(c["card_id"], k)] == 1 for c in cards for k in ("H", "T"))


def test_cards_build_valid_reports():
    for card in sim.load_cards():
        report = sim.report_for(card)
        assert report.evidence and report.comps.n >= 3
        assert card["reservation"] < card["buyer_max"] < card["listing"]["asking"]


@pytest.mark.parametrize("cond", ["H", "T"])
def test_never_below_floor_or_above_budget(cond):
    for card in sim.load_cards():
        for persona in sim.PERSONAS:
            r = sim.negotiate(card, persona, cond, "rules", random.Random(0))
            if not r.walked_away:
                assert card["reservation"] <= r.final_price <= card["buyer_max"]


def test_seller_floor_is_enforced_in_code():
    card = sim.load_cards()[0]
    s = sim.Seller(card, sim.PERSONAS[1], "rules", random.Random(0))
    move = s._enforce(sim.SellerMove("ok deal", "accept", None), buyer_offer=card["reservation"] - 500)
    assert move.action == "counter" and move.price == card["reservation"]


@pytest.mark.xfail(reason="Known parser bug for B: a refusal containing 'okay' with no price reads as agreement",
                   strict=False)
def test_refusal_with_okay_is_not_agreement():
    card = sim.load_cards()[0]
    buyer = sim.TireKickBuyer(card, max_rounds=6)
    buyer.open()
    state = apply_seller_reply(buyer.state, "okay I can't go that low")
    assert state.status != NegotiationStatus.AGREED
