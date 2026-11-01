from _fixtures import challenge, honest_report, shady_report

from tirekick.models import EvidenceType as T, LightName, LightObservation, Listing, ProofTakeAnalysis, Severity
from tirekick.verify.report_builder import build_report


def types(report):
    return {e.type for e in report.evidence}


def test_honest_is_yellow_because_of_recall():
    r = honest_report()
    assert r.verdict == Severity.YELLOW
    assert T.RECALL_FOUND in types(r) and T.POSITIVE in types(r)
    assert not [e for e in r.evidence if e.severity == Severity.RED]
    assert [e.id for e in r.evidence] == [f"EV-{i:02d}" for i in range(1, len(r.evidence) + 1)]
    assert r.fair_price_low == 4300 - 100 and r.fair_price_high == 4900 - 100


def test_shady_is_red_for_the_right_reasons():
    r = shady_report()
    assert r.verdict == Severity.RED
    assert {T.CODE_MISSING, T.VIN_INVALID, T.VIN_LISTING_MISMATCH, T.WARNING_LIGHT_HIDDEN} <= types(r)


def _listing(**kw):
    base = dict(listing_id="L", asking_price=9000, year=2015, make="Honda", model="Civic", mileage=80000)
    base.update(kw)
    return Listing(**base)


def _analysis(**kw):
    base = dict(video_path="x.mp4", code_read="K7Q2XM", code_matches=True, continuous_take=True,
                windshield_vin_read="1HGCM82633A004352")
    base.update(kw)
    return ProofTakeAnalysis(**base)


def test_odometer_lower_than_listed_is_red():
    r = build_report("D", _listing(), challenge(), _analysis(odometer_read=60000, odometer_unit="mi"), None, [], None, [])
    assert r.verdict == Severity.RED and T.ODOMETER_MISMATCH in types(r)


def test_odometer_km_conversion_matches():
    r = build_report("D", _listing(mileage=80000, mileage_unit="mi"), challenge(),
                     _analysis(odometer_read=128748, odometer_unit="km"), None, [], None, [])
    assert T.ODOMETER_MISMATCH not in types(r)


def test_non_north_american_bad_check_digit_is_only_yellow():
    r = build_report("D", _listing(), challenge(), _analysis(windshield_vin_read="JHMCM56557C404454"), None, [], None, [])
    vin_items = [e for e in r.evidence if e.type == T.VIN_INVALID]
    assert vin_items and vin_items[0].severity == Severity.YELLOW


def test_tpms_on_after_start_is_yellow_but_check_engine_on_is_red():
    a = _analysis(lights=[LightObservation(light=LightName.TPMS, lit_at_key_on=True, on_after_start=True)])
    assert build_report("D", _listing(), challenge(), a, None, [], None, []).verdict == Severity.YELLOW
    a = _analysis(lights=[LightObservation(light=LightName.CHECK_ENGINE, lit_at_key_on=True, on_after_start=True)])
    assert build_report("D", _listing(), challenge(), a, None, [], None, []).verdict == Severity.RED


def test_no_video_is_red():
    assert build_report("D", _listing(), challenge(), None, None, [], None, []).verdict == Severity.RED
