from _fixtures import challenge

from tirekick.models import LightName
from tirekick.verify.proof_take import LightOut, TakeObservation, merge_observations


def obs(ce_key_on, code="K7Q2XM", vin="1HGCM82633A004352", cont=True):
    return TakeObservation(code_read=code, continuous_take=cont, windshield_vin_read=vin,
                           lights=[LightOut(light=LightName.CHECK_ENGINE, lit_at_key_on=ce_key_on,
                                            on_after_start=False, confidence=0.8)], odometer_read=84000)


def light(a, name=LightName.CHECK_ENGINE):
    return next(l for l in a.lights if l.light == name)


def test_majority_vote_and_agreement():
    a = merge_observations([obs(False), obs(False), obs(True)], "x.mp4", challenge())
    assert light(a).lit_at_key_on is False and a.runs == 3 and a.agreement < 1.0


def test_tie_becomes_unknown():
    a = merge_observations([obs(False), obs(True), obs(None)], "x.mp4", challenge())
    assert light(a).lit_at_key_on is None


def test_code_and_vin_preference():
    a = merge_observations([obs(True, code="K7Q2XN"), obs(True, code="K7Q2XM"), obs(True, vin="1HGCM82643A004352")],
                           "x.mp4", challenge())
    assert a.code_matches and a.windshield_vin_read == "1HGCM82633A004352"


def test_any_cut_breaks_continuity():
    a = merge_observations([obs(True), obs(True, cont=False), obs(True)], "x.mp4", challenge())
    assert a.continuous_take is False
