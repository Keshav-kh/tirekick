import pytest
from _fixtures import honest_report

from tirekick.models import NegotiationState, Offer
from tirekick.negotiate import PolicyViolation, apply_seller_reply, check_offer, draft_offer, next_offer_amount
from tirekick.negotiate.policy import money_figures


def state(**kw):
    base = dict(deal_id="DEAL-1234", buyer_ceiling=5000, asking_price=4800)
    base.update(kw)
    return NegotiationState(**base)


def test_opening_offer_uses_comps_and_evidence():
    # min(comps.low 4300, 0.88*4800=4224) - recall impact 100 = 4124 -> round down to 4100
    assert next_offer_amount(state(), honest_report()) == 4100


def test_counter_moves_a_third_of_the_gap():
    assert next_offer_amount(state(last_offer=4100, last_seller_ask=4600), honest_report()) == 4250


def test_small_gap_meets_seller():
    assert next_offer_amount(state(last_offer=4500, last_seller_ask=4600), honest_report()) == 4600


def test_never_above_ceiling():
    assert next_offer_amount(state(buyer_ceiling=4200, last_offer=4100, last_seller_ask=4600), honest_report()) == 4200


def test_draft_offer_template_passes_policy():
    r = honest_report()
    offer = draft_offer(state(), r)
    check_offer(offer, state(), r)
    assert offer.amount == 4100 and offer.cites


@pytest.mark.parametrize("offer,msg", [
    (Offer(amount=5200, cites=[], message_text="Would you take $5,200?"), "ceiling"),
    (Offer(amount=4100, cites=["EV-99"], message_text="Would you take $4,100?"), "unknown"),
    (Offer(amount=4100, cites=[], message_text="Send a $200 deposit via Zelle"), "payment"),
    (Offer(amount=4100, cites=[], message_text="KBB says $3,900, so would you take $4,100?"), "prices not in the evidence"),
])
def test_violations(offer, msg):
    with pytest.raises(PolicyViolation, match=msg):
        check_offer(offer, state(), honest_report())


def test_money_figures():
    assert money_figures("$4,100 or AED 15,000 or 4.5k, but not 128,000 miles or 2003") == {4100, 15000, 4500}


def test_seller_reply_parsing():
    s = apply_seller_reply(state(last_offer=4100), "I can do 4,600")
    assert s.last_seller_ask == 4600 and s.status.value == "in_progress"
    s = apply_seller_reply(state(last_offer=4100), "ok deal")
    assert s.status.value == "agreed" and s.last_seller_ask == 4100
    s = apply_seller_reply(state(last_offer=4100), "4k is fine")
    assert s.status.value == "agreed" and s.last_seller_ask == 4000
