"""parse_listing (B6) with mocked model output: field mapping, code-side checks, fallbacks."""

import pytest

from tirekick.verify import listing as listing_mod
from tirekick.verify.listing import ListingExtract, parse_listing, prices_in_text, regex_extract
from tirekick.verify.muse import MuseError

TEXT = ("2015 Honda Civic LX - one owner! $9,400 OBO. 84k miles, clean title. "
        "VIN 19XFB2F59FE000000. Pickup in State College, PA")


@pytest.fixture
def model(monkeypatch):
    sent = []

    def install(extract=None, error=None):
        def fake_json(messages, schema, **kw):
            sent.append(messages)
            assert schema is ListingExtract
            if error:
                raise error
            return extract
        monkeypatch.setattr(listing_mod, "muse_json", fake_json)
        return sent
    return install


def test_maps_model_fields_and_metadata(model):
    sent = model(ListingExtract(title="2015 Honda Civic LX", asking_price=9400, currency="usd", year=2015,
                                make="Honda", model="Civic", trim="LX", mileage=84000, vin="19xfb2f59fe000000",
                                location="State College, PA"))
    l = parse_listing(text=TEXT, url="https://www.facebook.com/marketplace/item/123", listing_id="DEAL-1")
    assert (l.asking_price, l.currency, l.year, l.make, l.model, l.trim, l.mileage) == \
        (9400, "USD", 2015, "Honda", "Civic", "LX", 84000)
    assert l.vin == "19XFB2F59FE000000" and l.source == "facebook_marketplace" and l.listing_id == "DEAL-1"
    assert l.raw_text == TEXT
    assert sent[0][0]["role"] == "system" and TEXT in sent[0][1]["content"][1]["text"]


def test_no_price_raises_value_error(model):
    model(ListingExtract(title="Honda Civic", year=2015, make="Honda", model="Civic"))
    with pytest.raises(ValueError, match="No asking price"):
        parse_listing(text="2015 Honda Civic, message me for the price")


def test_needs_text_or_images():
    with pytest.raises(ValueError):
        parse_listing()


def test_screenshots_are_sent_as_images(model, tmp_path):
    shot = tmp_path / "s.jpg"
    shot.write_bytes(b"\xff\xd8\xff")
    sent = model(ListingExtract(asking_price=15000, currency="AED", make="Nissan", model="Patrol"))
    l = parse_listing(image_paths=[str(shot)], url="https://dubai.dubizzle.com/motors/x")
    assert l.currency == "AED" and l.source == "dubizzle"
    assert any(p["type"] == "image_url" for p in sent[0][1]["content"])


def test_price_not_in_text_is_corrected_in_code(model):
    model(ListingExtract(asking_price=8400, year=2015, make="Honda", model="Civic"))   # model misread
    assert parse_listing(text=TEXT).asking_price == 9400


def test_malformed_vin_is_dropped(model):
    model(ListingExtract(asking_price=9400, vin="19XFB2F59FE00"))
    assert parse_listing(text="2015 Civic $9,400").vin is None


def test_model_failure_falls_back_to_regex_parser(model):
    model(error=MuseError("503 after retries"))
    l = parse_listing(text=TEXT)
    assert (l.asking_price, l.year, l.make, l.model, l.trim, l.mileage, l.vin) == \
        (9400, 2015, "Honda", "Civic", "LX", 84000, "19XFB2F59FE000000")


def test_model_failure_without_text_is_a_value_error(model, tmp_path):
    shot = tmp_path / "s.jpg"
    shot.write_bytes(b"\xff\xd8\xff")
    model(error=MuseError("down"))
    with pytest.raises(ValueError):
        parse_listing(image_paths=[str(shot)])


@pytest.mark.parametrize("text,expected", [
    ("$4,800 obo", [(4800, "USD")]), ("asking 4.5k", [(4500, None)]), ("AED 15,000", [(15000, "AED")]),
    ("15000 AED, 2018, 120,000 km", [(15000, "AED")]), ("was $5,500 now $4,800", [(5500, "USD"), (4800, "USD")]),
    ("128,000 miles, 2003", []),
])
def test_prices_in_text(text, expected):
    assert prices_in_text(text) == expected


def test_regex_extract_km_dubizzle():
    e = regex_extract("2018 Nissan Patrol LE, 120,000 km, AED 95,000, Dubai")
    assert (e.year, e.make, e.model, e.trim, e.mileage, e.mileage_unit, e.asking_price, e.currency) == \
        (2018, "Nissan", "Patrol", "LE", 120000, "km", 95000, "AED")
