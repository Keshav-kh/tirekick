"""draft_offer (B8) on the model path with a mocked client: pass, retry, fallback, forbidden words, EV ids."""

import pytest
from _fixtures import honest_report

from tirekick.models import EvidenceType, NegotiationState, PriceComps
from tirekick.negotiate import PolicyViolation, check_offer, draft_offer, final_offer, walk_away_offer
from tirekick.negotiate.agent import clean_model_text, template_message
from tirekick.verify import muse

GOOD = "Thanks for the video! There's an airbag recall on this model, so would you take $4,100?"


def state(**kw):
    base = dict(deal_id="DEAL-1234", buyer_ceiling=5000, asking_price=4800)
    base.update(kw)
    return NegotiationState(**base)


@pytest.fixture
def model(monkeypatch):
    """Real (non-fake) mode with a key; Muse Spark replies come from a script."""
    monkeypatch.setenv("TIREKICK_FAKE_AI", "0")
    monkeypatch.setenv("META_API_KEY", "test-key")
    calls = []

    def install(*replies):
        queue = list(replies)

        def fake_chat(messages, **kw):
            calls.append(messages)
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        monkeypatch.setattr(muse, "chat_text", fake_chat)
        return calls
    return install


def no_ev(offer):
    assert "EV-" not in offer.message_text


def test_good_model_draft_passes(model):
    r = honest_report()
    calls = model(GOOD)
    offer = draft_offer(state(), r)
    assert offer.message_text == GOOD and offer.amount == 4100 and offer.cites
    check_offer(offer, state(), r)
    assert len(calls) == 1
    prompt = calls[0][1]["content"]
    assert "$4,100" in prompt and "recall" in prompt.lower() and "EV-" not in prompt


def test_stray_price_retried_once_then_template(model):
    r = honest_report()
    stray = "KBB says it's worth $3,900, so would you take $4,100?"
    calls = model(stray, stray)
    offer = draft_offer(state(), r)
    assert len(calls) == 2
    assert "rejected" in calls[1][1]["content"] and "3900" in calls[1][1]["content"]
    assert offer.message_text == template_message(4100, r, offer.cites, "USD")
    check_offer(offer, state(), r)
    no_ev(offer)


def test_stray_price_then_good_draft_uses_the_retry(model):
    calls = model("Would you take $4,100? I saw one for $3,500.", GOOD)
    offer = draft_offer(state(), honest_report())
    assert offer.message_text == GOOD and len(calls) == 2


@pytest.mark.parametrize("bad", [
    "Would you take $4,100? I can send a deposit today.",
    "Would you take $4,100? I can Zelle you right now.",
])
def test_deposit_or_zelle_draft_is_rejected(model, bad):
    r = honest_report()
    model(bad, bad)
    offer = draft_offer(state(), r)
    assert offer.message_text != bad and "deposit" not in offer.message_text.lower()
    assert "zelle" not in offer.message_text.lower()
    with pytest.raises(PolicyViolation, match="payment"):
        check_offer(offer.model_copy(update={"message_text": bad}), state(), r)


def test_ev_ids_are_stripped_from_model_text(model):
    r = honest_report()
    model("Thanks! There's an airbag recall (EV-03) [EV-01] so would you take $4,100? EV-2")
    offer = draft_offer(state(), r)
    no_ev(offer)
    assert offer.message_text == "Thanks! There's an airbag recall so would you take $4,100?"
    check_offer(offer, state(), r)


def test_too_long_or_missing_amount_is_retried(model):
    calls = model("x" * 400 + " $4,100", "Would you take a bit less?", GOOD)
    offer = draft_offer(state(), honest_report())
    assert len(calls) == 2 and offer.message_text != GOOD           # 2 tries max, then template
    assert "320" in calls[1][1]["content"]
    calls = model("Would you consider less?", GOOD)
    assert draft_offer(state(), honest_report()).message_text == GOOD
    assert "$4,100" in calls[-1][1]["content"].split("rejected:")[1]


def test_api_failure_falls_back_to_template_without_retry(model):
    calls = model(muse.MuseError("503 after retries"))
    offer = draft_offer(state(), honest_report())
    assert len(calls) == 1 and offer.message_text.startswith("Thanks for the video!")


def test_no_evidence_and_no_comps_never_asks_for_unsupported_reduction():
    r = honest_report()
    r = r.model_copy(update={
        "evidence": [e for e in r.evidence if e.type != EvidenceType.RECALL_FOUND],
        "comps": PriceComps(n=0, note="unavailable"),
    })
    offer = draft_offer(state(), r)
    assert offer.amount == 4800 and not offer.cites           # asking price, nothing to cite
    check_offer(offer, state(), r)
    low_ceiling = state(buyer_ceiling=4500)
    offer = draft_offer(low_ceiling, r)
    assert offer.is_walk_away                                 # can't justify going below asking
    check_offer(offer, low_ceiling, r)


def test_seller_text_never_contains_ids_on_any_path():
    r = honest_report()
    for offer in (draft_offer(state(), r), final_offer(state(last_offer=4100, last_seller_ask=4300)),
                  walk_away_offer(state())):
        no_ev(offer)


def test_clean_model_text():
    assert clean_model_text('"Hi (EV-01), would you take $4,100?"') == "Hi, would you take $4,100?"
    assert clean_model_text("  Hi\n\nthere  ") == "Hi there"
