"""build_report: one test per SPEC section 6.3 check (C1-C13), all from hand-built inputs."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from _fixtures import challenge

from tirekick.models import (
    ChatMessage, ChatRole, EvidenceType as T, LightName as L, LightObservation, Listing, PriceComps,
    ProofTakeAnalysis, Recall, Severity as S, VinDecode,
)
from tirekick.verify import report_builder as rb
from tirekick.verify.report_builder import build_report, engine_mismatch, extract_evidence_frames
from tirekick.verify.scam import scan_chat

VIN = "1HGCM82633A004352"          # valid North-American check digit
ALL = (L.CHECK_ENGINE, L.AIRBAG, L.ABS, L.BATTERY, L.OIL_PRESSURE, L.BRAKE, L.TPMS)


def listing(**kw):
    base = dict(listing_id="L", asking_price=4800, year=2003, make="Honda", model="Accord", trim="EX",
                engine="2.4L 4cyl", mileage=128000, mileage_unit="mi", vin=VIN)
    base.update(kw)
    return Listing(**base)


def lights(**over):
    """All seven lights sweep on at key-on and go off after start, unless overridden."""
    out = []
    for name in ALL:
        key_on, after = over.get(name.value, (True, False))
        out.append(LightObservation(light=name, lit_at_key_on=key_on, on_after_start=after,
                                    key_on_timestamp_s=17, after_start_timestamp_s=26, confidence=0.9))
    return out


def clean(**kw):
    base = dict(video_path="x.mp4", duration_s=40, runs=3, code_read="K7Q2XM", code_matches=True,
                code_timestamp_s=3, continuous_take=True, windshield_vin_read=VIN, windshield_vin_timestamp_s=3,
                door_vin_read=VIN, door_vin_timestamp_s=10, lights=lights(), key_on_timestamp_s=17,
                engine_start_timestamp_s=24, odometer_read=129000, odometer_unit="mi", odometer_timestamp_s=20,
                engine_cold=True, temp_gauge_timestamp_s=21)
    base.update(kw)
    return ProofTakeAnalysis(**base)


def decode(**kw):
    base = dict(vin=VIN, check_digit_valid=True, north_american=True, year=2003, make="Honda",
                model="Accord", trim="EX", engine="2.4L 4cyl")
    base.update(kw)
    return VinDecode(**base)


def report(analysis=None, vin_decode=None, recalls=(), comps=None, chat=(), lst=None):
    return build_report("DEAL-1", lst or listing(), challenge(), analysis if analysis is not None else clean(),
                        vin_decode, list(recalls), comps, list(chat))


def items(r, type_):
    return [e for e in r.evidence if e.type == type_]


def only(r, type_):
    found = items(r, type_)
    assert len(found) == 1, [e.summary for e in r.evidence]
    return found[0]


# --------------------------------------------------------------------------- baseline


def test_clean_take_is_green_with_positive_items():
    r = report(vin_decode=decode())
    assert r.verdict == S.GREEN, [e.summary for e in r.evidence]
    assert {e.severity for e in r.evidence} == {S.GREEN}
    assert len(items(r, T.POSITIVE)) == 4   # VIN pair, lights, odometer, decode


# --------------------------------------------------------------------------- C1-C13


def test_c1_code_missing_is_red():
    e = only(report(clean(code_read="K7Q2XN", code_matches=False)), T.CODE_MISSING)
    assert e.severity == S.RED and "K7Q2XM" in e.detail and e.clip_start_s == 3


def test_c2_cuts_are_red_with_timestamps():
    e = only(report(clean(continuous_take=False, cut_timestamps_s=[6.0, 12.5])), T.TAKE_HAS_CUTS)
    assert e.severity == S.RED and "6s, 12.5s" in e.summary and e.clip_start_s == 6.0


@pytest.mark.parametrize("read", [None, "", "1HGCM8263", "1HGCM82633A0043521"])
def test_c3_unreadable_or_malformed_vin_is_yellow(read):
    r = report(clean(windshield_vin_read=read))
    assert only(r, T.VIN_UNREADABLE).severity == S.YELLOW
    assert not items(r, T.VIN_INVALID) and not items(r, T.VIN_MISMATCH_DOORS)


def test_c3_bad_check_digit_red_for_north_american_yellow_otherwise():
    bad_na = "1HGCM82643A004352"
    r = report(clean(windshield_vin_read=bad_na, door_vin_read=bad_na), lst=listing(vin=None))
    assert only(r, T.VIN_INVALID).severity == S.RED
    bad_import = "JHMCM56557C404454"
    r = report(clean(windshield_vin_read=bad_import, door_vin_read=bad_import), lst=listing(vin=None))
    assert only(r, T.VIN_INVALID).severity == S.YELLOW and r.verdict == S.YELLOW


def test_c4_door_vin_mismatch_is_red():
    e = only(report(clean(door_vin_read="1HGCM82633A004353")), T.VIN_MISMATCH_DOORS)
    assert e.severity == S.RED and e.clip_start_s == 10


def test_c5_video_vin_differs_from_listing_vin_is_red():
    other = "1M8GDM9AXKP042788"
    r = report(clean(windshield_vin_read=other, door_vin_read=other))
    assert only(r, T.VIN_LISTING_MISMATCH).severity == S.RED


def test_c5_decode_year_make_model_mismatch_is_red():
    r = report(vin_decode=decode(year=2007, model="Civic"))
    e = only(r, T.VIN_LISTING_MISMATCH)
    assert e.severity == S.RED and "2007 Honda Civic" in e.summary and r.verdict == S.RED


def test_c5_trim_and_engine_mismatch_are_yellow_with_price_impact():
    r = report(vin_decode=decode(trim="LX", engine="2.4L 4cyl"))
    e = only(r, T.VIN_LISTING_MISMATCH)
    assert e.severity == S.YELLOW and e.price_impact == rb.TRIM_MISMATCH_IMPACT and "LX" in e.summary
    r = report(vin_decode=decode(trim="EX", engine="3.0L 6cyl"))
    e = only(r, T.VIN_LISTING_MISMATCH)
    assert e.severity == S.YELLOW and e.price_impact == rb.ENGINE_MISMATCH_IMPACT and "3.0L" in e.summary
    assert r.verdict == S.YELLOW


def test_c5_fuzzy_matches_are_not_mismatches():
    r = report(lst=listing(make="Chevy", model="Malibu", trim="LT", engine="2.4L I4"),
               vin_decode=decode(make="Chevrolet", model="Malibu", trim="LT Sedan", engine="2.4L 4cyl"),
               analysis=clean(windshield_vin_read=None))
    assert not items(r, T.VIN_LISTING_MISMATCH)
    r = report(vin_decode=decode(trim=None, engine=None))   # unknown decoded trim: no mismatch
    assert not items(r, T.VIN_LISTING_MISMATCH)


def test_c6_recalls_are_yellow_one_per_system_capped():
    recalls = [Recall(campaign_number=f"R{i}", component=c, summary="x")
               for i, c in enumerate(["AIR BAGS:FRONTAL", "AIR BAGS:SIDE", "ELECTRICAL", "STEERING", "FUEL"])]
    r = report(recalls=recalls)
    found = items(r, T.RECALL_FOUND)
    assert len(found) == rb.RECALL_MAX_ITEMS and {e.severity for e in found} == {S.YELLOW}
    assert sum(e.price_impact for e in found) <= rb.RECALL_IMPACT_CAP
    assert "Air Bags" in found[0].summary
    assert any("nhtsa.gov/recalls" in q for q in r.inspection_questions)


def test_c7_must_light_dark_at_key_on_is_red_other_lights_yellow():
    r = report(clean(lights=lights(check_engine=(False, False))))
    e = only(r, T.WARNING_LIGHT_HIDDEN)
    assert e.severity == S.RED and "check-engine" in e.summary and e.clip_start_s == 17
    r = report(clean(lights=lights(tpms=(False, False))))
    assert only(r, T.WARNING_LIGHT_HIDDEN).severity == S.YELLOW


def test_c7_pre_1996_cars_are_not_held_to_must_light():
    r = report(clean(lights=lights(abs=(False, False))), lst=listing(year=1994))
    assert only(r, T.WARNING_LIGHT_HIDDEN).severity == S.YELLOW


def test_c7_no_bulb_check_shown_is_yellow_not_silently_green():
    for ls in ([], lights(**{n.value: (None, None) for n in ALL})):
        r = report(clean(lights=ls))
        e = only(r, T.WARNING_LIGHT_HIDDEN)
        assert e.severity == S.YELLOW and "wasn't clearly shown" in e.summary


def test_c8_light_on_after_start_red_if_critical_else_yellow():
    for name in ("check_engine", "airbag", "oil_pressure", "brake"):
        e = only(report(clean(lights=lights(**{name: (True, True)}))), T.WARNING_LIGHT_ON)
        assert e.severity == S.RED and e.price_impact == 0 and e.clip_start_s == 26
    e = only(report(clean(lights=lights(battery=(True, True)))), T.WARNING_LIGHT_ON)
    assert e.severity == S.YELLOW and e.price_impact == rb.LIGHT_ON_IMPACT


def test_c9_odometer_lower_red_higher_yellow_with_capped_impact():
    e = only(report(clean(odometer_read=100000)), T.ODOMETER_MISMATCH)
    assert e.severity == S.RED and "100,000" in e.summary
    e = only(report(clean(odometer_read=140000)), T.ODOMETER_MISMATCH)
    assert e.severity == S.YELLOW and e.price_impact == 1200        # 0.10 x 12,000 extra miles
    e = only(report(clean(odometer_read=300000)), T.ODOMETER_MISMATCH)
    assert e.price_impact == rb.EXTRA_MILES_CAP
    r = report(clean(odometer_read=130000))                           # within 5%
    assert not items(r, T.ODOMETER_MISMATCH)


def test_c9_units_are_converted():
    r = report(clean(odometer_read=206000, odometer_unit="km"))      # 128,000 mi
    assert not items(r, T.ODOMETER_MISMATCH)


def test_c10_warm_engine_is_yellow_unknown_is_not_flagged():
    assert only(report(clean(engine_cold=False)), T.ENGINE_WARM).severity == S.YELLOW
    assert not items(report(clean(engine_cold=None)), T.ENGINE_WARM)


def test_c11_screen_replay_is_red():
    assert only(report(clean(screen_replay_suspected=True)), T.SCREEN_REPLAY).severity == S.RED


def test_c12_chat_scam_signals_pass_through_as_red():
    chat = scan_chat([ChatMessage(role=ChatRole.SELLER, text="Pay with gift cards and I'll ship it")],
                     listing(), None)
    r = report(chat=chat)
    found = items(r, T.SCAM_SIGNAL)
    assert len(found) == 2 and {e.severity for e in found} == {S.RED} and r.verdict == S.RED


def test_c13_price_far_below_comps_yellow_alone_red_with_scam():
    comps = PriceComps(low=6500, median=7500, high=9000, n=5, sources=["https://a", "https://b", "https://c"])
    r = report(comps=comps)                                          # 4,800 < 0.7 x 7,500
    e = only(r, T.PRICE_BELOW_MARKET)
    assert e.severity == S.YELLOW and "7,500" in e.summary
    chat = scan_chat([ChatMessage(role=ChatRole.SELLER, text="send a deposit to hold it for you")], listing(), comps)
    assert only(report(comps=comps, chat=chat), T.PRICE_BELOW_MARKET).severity == S.RED
    assert not items(report(comps=PriceComps(low=4500, median=5000, high=5600, n=4)), T.PRICE_BELOW_MARKET)


# --------------------------------------------------------------------------- report-level rules


def test_failed_analysis_gives_one_honest_red_item():
    r = report(ProofTakeAnalysis(video_path="x.mp4", runs=0, model_notes="analysis failed: timeout"))
    video = [e for e in r.evidence if e.source.value == "video"]
    assert len(video) == 1 and video[0].severity == S.RED and "couldn't be analyzed" in video[0].summary


def test_ids_verdict_fair_price_and_questions():
    comps = PriceComps(low=4300, median=4900, high=5600, n=5)
    r = report(clean(odometer_read=140000, engine_cold=False), comps=comps,
               recalls=[Recall(campaign_number="R1", component="AIR BAGS", summary="x")])
    assert [e.id for e in r.evidence] == [f"EV-{i:02d}" for i in range(1, len(r.evidence) + 1)]
    assert r.verdict == S.YELLOW
    impact = 1200 + rb.RECALL_IMPACT
    assert (r.fair_price_low, r.fair_price_high) == (4300 - impact, 4900 - impact)
    assert len(r.inspection_questions) == 4    # odometer, warm engine, recall, VIN recall check
    assert any("recall was completed" in q for q in r.inspection_questions)


def test_fair_price_clamped_to_half_of_asking():
    comps = PriceComps(low=2000, median=2600, n=3)
    r = report(clean(odometer_read=300000), comps=comps)
    assert r.fair_price_low == r.fair_price_high == 2400


@pytest.mark.parametrize("listed,decoded,expected", [
    ("3.0L V6", "3.0L 6cyl", False), ("2.4L", "3.0L 6cyl", True), ("V6", "2.4L 4cyl", True),
    ("1.8 I4", "1.8L 4cyl", False), (None, "2.4L 4cyl", False), ("turbo", "2.0L 4cyl", False),
])
def test_engine_mismatch(listed, decoded, expected):
    assert engine_mismatch(listed, decoded) is expected


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_evidence_frames_written_for_timestamped_items(tmp_path):
    clip = tmp_path / "clip.mp4"
    script = Path(__file__).resolve().parents[1] / "scripts" / "make_synthetic_clip.py"
    subprocess.run([sys.executable, str(script), "--out", str(clip), "--duration", "4", "--cut-at", "2"],
                   check=True, capture_output=True)
    r = report(clean(code_matches=False, code_timestamp_s=1.0, video_path=str(clip)))
    extract_evidence_frames(r, str(clip))
    code_item = only(r, T.CODE_MISSING)
    assert code_item.frame_path and Path(code_item.frame_path).stat().st_size > 0
    assert Path(code_item.frame_path).name == f"{code_item.id}.jpg"
