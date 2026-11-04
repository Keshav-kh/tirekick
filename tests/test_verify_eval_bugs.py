"""Regression tests for the 4 bugs C's evaluation found (eval/RESULTS.md section 5 on eval-demo)."""

import httpx
import respx
from _fixtures import challenge

from tirekick.models import EvidenceType as T, LightName as L, LightObservation, Listing, NegotiationState
from tirekick.models import ProofTakeAnalysis, Severity as S
from tirekick.negotiate import apply_seller_reply
from tirekick.negotiate.agent import is_acceptance
from tirekick.verify import proof_take
from tirekick.verify.recalls import RECALLS_URL, lookup_recalls, nhtsa_make_model
from tirekick.verify.report_builder import build_report

VIN = "1HGCM82633A004352"
LISTING = Listing(listing_id="L", asking_price=4800, year=2014, make="Honda", model="Civic", vin=VIN)


def analysis(lights):
    return ProofTakeAnalysis(video_path="x.mp4", runs=3, code_read="K7Q2XM", code_matches=True,
                             continuous_take=True, windshield_vin_read=VIN, door_vin_read=VIN, lights=lights,
                             key_on_timestamp_s=17)


def lit(name, key_on=True):
    return LightObservation(light=name, lit_at_key_on=key_on, on_after_start=False)


# Bug 1: blurry dashboard passed ("can't tell" on a must-light + a green "all lights came on" line)
def test_bug1_unconfirmed_must_light_is_yellow_and_no_green_line():
    r = build_report("D", LISTING, challenge(), analysis(
        [lit(L.CHECK_ENGINE, None), lit(L.AIRBAG), lit(L.ABS), lit(L.BATTERY), lit(L.OIL_PRESSURE)]),
        None, [], None, [])
    hidden = [e for e in r.evidence if e.type == T.WARNING_LIGHT_HIDDEN]
    assert len(hidden) == 1 and hidden[0].severity == S.YELLOW and "check-engine" in hidden[0].summary
    assert not any("came on at key-on" in e.summary for e in r.evidence if e.type == T.POSITIVE)
    assert r.verdict == S.YELLOW


def test_bug1_must_light_missing_from_report_counts_too():
    r = build_report("D", LISTING, challenge(), analysis([lit(L.BATTERY), lit(L.OIL_PRESSURE)]),
                     None, [], None, [])
    hidden = [e for e in r.evidence if e.type == T.WARNING_LIGHT_HIDDEN]
    assert len(hidden) == 3 and {e.severity for e in hidden} == {S.YELLOW}


def test_bug1_all_must_lights_seen_still_green():
    r = build_report("D", LISTING, challenge(), analysis(
        [lit(L.CHECK_ENGINE), lit(L.AIRBAG), lit(L.ABS), lit(L.TPMS, None)]), None, [], None, [])
    assert r.verdict == S.GREEN


# Bug 2: no ffmpeg on the server must not look like "saw nothing wrong"
def test_bug2_missing_ffmpeg_is_red_not_a_silent_pass(tmp_path, monkeypatch):
    clip = tmp_path / "x.mp4"
    clip.write_bytes(b"\x00" * 100)
    monkeypatch.setattr(proof_take, "_ffmpeg_ok", lambda: False)
    monkeypatch.setenv("MUSE_VIDEO_MODE", "frames")
    a = proof_take.analyze_proof_take(str(clip), challenge(), LISTING)
    assert a.runs == 0 and "ffmpeg" in a.model_notes
    r = build_report("D", LISTING, challenge(), a, None, [], None, [])
    assert r.verdict == S.RED and "couldn't be analyzed" in r.evidence[0].summary


# Bug 3: "okay I can't go that low" was parsed as agreement
def test_bug3_refusal_with_okay_is_not_agreement():
    s = NegotiationState(deal_id="D", buyer_ceiling=5000, asking_price=4800, last_offer=4100)
    for text in ("okay I can't go that low", "ok no", "Yes that's too low", "sure, but no way",
                 "No, sorry", "ok that's not going to work"):
        assert apply_seller_reply(s, text).status.value == "in_progress", text
    for text in ("ok deal", "Sure, works for me", "No problem, deal!", "yes"):
        assert is_acceptance(text), text
    assert apply_seller_reply(s, "ok deal").status.value == "agreed"


# Bug 4: every Scion 400'd at the recalls API (vPIC: Toyota / "Scion tC"; NHTSA wants Scion / tC)
def test_bug4_scion_mapping():
    assert nhtsa_make_model("Toyota", "Scion tC") == ("Scion", "tC")
    assert nhtsa_make_model("TOYOTA", "Scion xB") == ("Scion", "xB")
    assert nhtsa_make_model("Scion", "tC") == ("Scion", "tC")
    assert nhtsa_make_model("Toyota", "Corolla") == ("Toyota", "Corolla")


@respx.mock
def test_bug4_scion_recalls_query_uses_scion_make():
    route = respx.get(RECALLS_URL).mock(return_value=httpx.Response(200, json={"results": [
        {"NHTSACampaignNumber": "15V000000", "Component": "AIR BAGS"}]}))
    assert len(lookup_recalls("Toyota", "Scion tC", 2005)) == 1
    assert dict(route.calls[0].request.url.params) == {"make": "Scion", "model": "tC", "modelYear": "2005"}
