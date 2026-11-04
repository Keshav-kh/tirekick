"""scan_chat (B10): rules on the scripted chat corpus, plus the verbatim-checked model pass."""

import json
from pathlib import Path

import pytest

from tirekick.models import ChatMessage, ChatRole, Listing, Severity
from tirekick.verify import muse, scam
from tirekick.verify.scam import ChatFinding, ChatFindings, rule_findings, scan_chat, verbatim_in

CHATS = sorted((Path(__file__).parent / "fixtures" / "chats").glob("*.json"))
L = Listing(listing_id="L", asking_price=4800, year=2015, make="Honda", model="Civic")


def load(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["label"], [ChatMessage(**m) for m in data["messages"]]


def test_corpus_has_ten_of_each():
    labels = [load(p)[0] for p in CHATS]
    assert labels.count("scam") >= 10 and labels.count("legit") >= 10


@pytest.mark.parametrize("path", [p for p in CHATS if p.name.startswith("scam")], ids=lambda p: p.stem)
def test_rules_catch_every_scam_chat(path):
    _, msgs = load(path)
    found = scan_chat(msgs, L, None)
    assert found and all(e.severity == Severity.RED for e in found)


def test_rules_false_alarm_rate_on_legit_chats_under_ten_percent():
    legit = [p for p in CHATS if p.name.startswith("legit")]
    alarms = [p.stem for p in legit if scan_chat(load(p)[1], L, None)]
    assert len(alarms) / len(legit) < 0.10, alarms


def seller(text):
    return ChatMessage(role=ChatRole.SELLER, text=text)


@pytest.mark.parametrize("text,key", [
    ("I'll ship the car to you", "shipping"),
    ("I'm currently out of the country", "absent"),
    ("Reserve it with a reservation fee", "deposit"),
])
def test_new_rule_patterns(text, key):
    assert key in rule_findings([seller(text)])


@pytest.mark.parametrize("text", [
    "No deposit needed", "I'm not shipping it, local pickup only", "Moving out of state next month",
    "Happy to do a video and an inspection",
])
def test_negated_or_honest_phrases_not_flagged(text):
    assert rule_findings([seller(text)]) == {}


def test_verbatim_check():
    texts = ["Hurry, three other buyers are coming tonight!", "Text me on   Telegram instead"]
    assert verbatim_in("three other buyers are coming tonight", texts) == texts[0]
    assert verbatim_in("Text me on Telegram", texts) == texts[1]          # whitespace normalized
    assert verbatim_in("other buyers are coming", texts) is not None
    assert verbatim_in("three buyers are coming tonight", texts) is None  # paraphrase
    assert verbatim_in("hurry", texts) is None                            # too short to be evidence


@pytest.fixture
def model(monkeypatch):
    """Turn the model pass on (real mode + a key) and script what Muse Spark returns."""
    monkeypatch.setenv("TIREKICK_FAKE_AI", "0")
    monkeypatch.setenv("META_API_KEY", "test-key")
    calls = []

    def install(findings=None, error=None):
        def fake_json(messages, schema, **kw):
            calls.append(messages)
            if error:
                raise error
            return ChatFindings(findings=findings or [])
        monkeypatch.setattr(muse, "muse_json", fake_json)
        return calls
    return install


def test_model_finding_kept_only_if_verbatim(model):
    msgs = [seller("Hurry, three other buyers are coming tonight!"), seller("Text me on Telegram instead")]
    calls = model([
        ChatFinding(category="pressure_or_urgency", quote="three other buyers are coming tonight"),
        ChatFinding(category="move_off_platform", quote="Please message me on WhatsApp"),   # not in the chat
        ChatFinding(category="move_off_platform", quote="Text me on Telegram instead"),
    ])
    found = scan_chat(msgs, L, None)
    assert len(calls) == 1
    assert [e.summary for e in found] == [scam.MODEL_SUMMARY["pressure_or_urgency"],
                                          scam.MODEL_SUMMARY["move_off_platform"]]
    assert {e.severity for e in found} == {Severity.YELLOW}            # code decides: soft categories
    assert "three other buyers" in found[0].detail


def test_model_severity_comes_from_category_and_rules_run_first(model):
    msgs = [seller("Pay with gift cards please"), seller("I need the money sent before you come over")]
    model([ChatFinding(category="deposit_or_prepayment", quote="I need the money sent before you come over")])
    found = scan_chat(msgs, L, None)
    assert found[0].summary == scam.REASONS["untraceable"]                # rule finding first
    assert found[1].severity == Severity.RED                              # red category, decided in code


def test_model_failure_keeps_rule_findings(model):
    model(error=muse.MuseError("boom"))
    found = scan_chat([seller("Pay with gift cards please")], L, None)
    assert [e.summary for e in found] == [scam.REASONS["untraceable"]]


def test_model_pass_skipped_in_fake_mode(monkeypatch):
    monkeypatch.setenv("META_API_KEY", "test-key")          # TIREKICK_FAKE_AI=1 from conftest
    monkeypatch.setattr(muse, "muse_json", lambda *a, **k: pytest.fail("model called in fake mode"))
    assert scan_chat([seller("hello")], L, None) == []
