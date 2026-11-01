import pytest

from tirekick.verify.vin import is_north_american, normalize_vin, parse_vpic_row, validate_vin


@pytest.mark.parametrize("vin", ["1HGCM82633A004352", "1M8GDM9AXKP042788", "11111111111111111"])
def test_valid_check_digits(vin):
    assert validate_vin(vin) == (True, vin)


def test_bad_check_digit():
    assert validate_vin("1HGCM82643A004352")[0] is False


@pytest.mark.parametrize("vin", ["1HGCM82633A00435", "1HGCM82633A0043521", "1HGCM8263IA004352", "1HGCM8263OA004352", ""])
def test_malformed(vin):
    assert validate_vin(vin)[0] is False


def test_normalize():
    assert normalize_vin(" 1hgcm8-2633a004352 ") == "1HGCM82633A004352"
    assert validate_vin("1hgcm82633a004352") == (True, "1HGCM82633A004352")


def test_north_american():
    assert is_north_american("1HGCM82633A004352")
    assert is_north_american("5YJSA1E2XHF000000")
    assert not is_north_american("JHMCM56557C404453")
    assert not is_north_american("WVWZZZ1JZXW000001")


def test_parse_vpic_row():
    row = {"ModelYear": "2003", "Make": "HONDA", "Model": "Accord", "Trim": "EX",
           "DisplacementL": "2.4", "EngineCylinders": "4", "BodyClass": "Sedan/Saloon",
           "ErrorCode": "0", "ErrorText": "0 - VIN decoded clean."}
    d = parse_vpic_row("1HGCM82633A004352", row)
    assert (d.year, d.make, d.model, d.trim, d.engine) == (2003, "Honda", "Accord", "EX", "2.4L 4cyl")
    assert d.check_digit_valid and d.north_american and d.error_text == ""
