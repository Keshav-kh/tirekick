"""run_verification (B7) in real mode with every external call mocked; plus fake mode."""

import threading
import time

import pytest
from _fixtures import challenge

from tirekick import verify
from tirekick.models import ChatMessage, ChatRole, Deal, Listing, PriceComps, ProofTakeAnalysis, Severity, VinDecode
from tirekick.verify import fake

VIN = "1HGCM82633A004352"


def deal(**kw):
    listing = Listing(listing_id="L", asking_price=4800, year=2003, make="Honda", model="Accord", trim="EX",
                      mileage=128000, vin=VIN)
    base = dict(deal_id="DEAL-1", buyer_wa_id="1", listing=listing, challenge=challenge())
    base.update(kw)
    return Deal(**base)


@pytest.fixture
def real(monkeypatch):
    """Real mode, no key: mock the four network-facing calls and record what they got."""
    monkeypatch.setenv("TIREKICK_FAKE_AI", "0")
    seen = {}

    def analysis(video, ch, listing, runs):
        seen["runs"] = runs
        seen["analysis_thread"] = threading.get_ident()
        seen["analysis_span"] = [time.monotonic()]
        time.sleep(0.2)
        seen["analysis_span"].append(time.monotonic())
        return fake.analyze_proof_take(video, ch, listing, runs)

    def comps(listing):
        seen["comps_thread"] = threading.get_ident()
        seen["comps_span"] = [time.monotonic()]
        time.sleep(0.2)
        seen["comps_span"].append(time.monotonic())
        return PriceComps(low=4300, median=4900, high=5600, n=4, sources=["https://a.example"])

    def decode(vin):
        seen["vin"] = vin
        return VinDecode(vin=vin, check_digit_valid=True, north_american=True, year=2003, make="Honda",
                         model="Accord", trim="EX")

    def recalls(make, model, year):
        seen["recalls"] = (make, model, year)
        return []

    from tirekick.verify import comps as comps_mod, proof_take, recalls as recalls_mod, vin as vin_mod
    monkeypatch.setattr(proof_take, "analyze_proof_take", analysis)
    monkeypatch.setattr(comps_mod, "price_comps", comps)
    monkeypatch.setattr(vin_mod, "decode_vin", decode)
    monkeypatch.setattr(recalls_mod, "lookup_recalls", recalls)
    return seen


def test_real_mode_wiring_and_parallel_comps(real, monkeypatch):
    monkeypatch.setenv("TIREKICK_RUNS", "1")
    r = verify.run_verification(deal(), "clips/honest.mp4")
    (a0, a1), (c0, c1) = real["analysis_span"], real["comps_span"]
    assert c0 < a1 and a0 < c1                               # analysis and comps ran at the same time
    assert real["analysis_thread"] != real["comps_thread"]
    assert real["runs"] == 1 and real["vin"] == VIN and real["recalls"] == ("Honda", "Accord", 2003)
    assert r.verdict == Severity.GREEN and r.comps.n == 4


def test_listing_vin_used_when_video_vin_unreadable(real, monkeypatch):
    from tirekick.verify import proof_take
    monkeypatch.setattr(proof_take, "analyze_proof_take",
                        lambda v, c, l, runs: ProofTakeAnalysis(video_path=v, runs=1, windshield_vin_read="1HGCM8"))
    verify.run_verification(deal(), "x.mp4")
    assert real["vin"] == VIN


def test_optional_steps_failing_still_builds_report(real, monkeypatch):
    from tirekick.verify import comps as comps_mod, vin as vin_mod

    def boom(*a):
        raise RuntimeError("network down")
    monkeypatch.setattr(comps_mod, "price_comps", boom)
    monkeypatch.setattr(vin_mod, "decode_vin", boom)
    r = verify.run_verification(deal(chat=[ChatMessage(role=ChatRole.SELLER, text="pay with gift cards")]), "x.mp4")
    assert r.comps is None and r.vin_decode is None and r.verdict == Severity.RED


def test_fake_mode_still_works():
    r = verify.run_verification(deal(), "clips/shady_accord.mp4")
    assert r.verdict == Severity.RED
    assert verify.run_verification(deal(), "clips/honest.mp4").verdict == Severity.YELLOW


def test_runs_setting(monkeypatch):
    from tirekick.verify.pipeline import runs_setting
    assert runs_setting() == 3
    monkeypatch.setenv("TIREKICK_RUNS", "junk")
    assert runs_setting() == 3
    monkeypatch.setenv("TIREKICK_RUNS", "0")
    assert runs_setting() == 1

