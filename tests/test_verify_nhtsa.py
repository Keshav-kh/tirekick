"""decode_vin / lookup_recalls (B1/B2): disk cache, retry on 429/5xx, error handling. Mocked with respx."""

import httpx
import pytest
import respx

from tirekick import config
from tirekick.verify import http
from tirekick.verify.recalls import RECALLS_URL, lookup_recalls
from tirekick.verify.vin import decode_vin

VIN = "1HGCM82633A004352"
VPIC = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{VIN}"
ROW = {"ModelYear": "2003", "Make": "HONDA", "Model": "Accord", "Trim": "EX", "DisplacementL": "2.4",
       "EngineCylinders": "4", "BodyClass": "Coupe", "ErrorCode": "0", "ErrorText": "0 - VIN decoded clean."}
RECALL = {"results": [{"NHTSACampaignNumber": "15V320000", "Component": "AIR BAGS", "Summary": "Inflator",
                       "Consequence": "c", "Remedy": "r", "ReportReceivedDate": "28/05/2015"}]}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(http, "_sleep", sleeps.append)
    return sleeps


@respx.mock
def test_decode_cached_on_disk():
    route = respx.get(VPIC).mock(return_value=httpx.Response(200, json={"Results": [ROW]}))
    d = decode_vin(VIN)
    assert (d.year, d.make, d.model, d.engine) == (2003, "Honda", "Accord", "2.4L 4cyl")
    assert decode_vin(VIN.lower()) == d and route.call_count == 1
    assert (config.DATA_DIR / "cache" / "vpic" / f"{VIN}.json").exists()


@respx.mock
def test_decode_retries_5xx_and_429(no_sleep):
    route = respx.get(VPIC).mock(side_effect=[httpx.Response(503), httpx.Response(429),
                                              httpx.Response(200, json={"Results": [ROW]})])
    assert decode_vin(VIN).make == "Honda"
    assert route.call_count == 3 and no_sleep == [1.0, 2.0]


@respx.mock
def test_decode_gives_up_after_backoff(no_sleep):
    respx.get(VPIC).mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        decode_vin(VIN)
    assert no_sleep == [1.0, 2.0, 4.0]


@respx.mock
def test_empty_decode_not_cached():
    route = respx.get(VPIC).mock(return_value=httpx.Response(200, json={"Results": [{"ErrorCode": "11"}]}))
    decode_vin(VIN)
    decode_vin(VIN)
    assert route.call_count == 2


@respx.mock
def test_recalls_cached_and_parsed():
    route = respx.get(RECALLS_URL).mock(return_value=httpx.Response(200, json=RECALL))
    r = lookup_recalls("Honda", "Accord", 2003)
    assert [x.campaign_number for x in r] == ["15V320000"] and r[0].component == "AIR BAGS"
    assert lookup_recalls("HONDA", "accord", 2003) == r and route.call_count == 1
    assert dict(route.calls[0].request.url.params) == {"make": "Honda", "model": "Accord", "modelYear": "2003"}


@respx.mock
def test_recalls_unknown_model_is_empty_not_an_error(no_sleep):
    respx.get(RECALLS_URL).mock(return_value=httpx.Response(400, json={"message": "bad"}))
    assert lookup_recalls("Nope", "Car", 2003) == [] and no_sleep == []


@respx.mock
def test_recalls_timeout_retried(no_sleep):
    route = respx.get(RECALLS_URL).mock(side_effect=[httpx.ConnectTimeout("t"), httpx.Response(200, json=RECALL)])
    assert len(lookup_recalls("Honda", "Civic", 2015)) == 1 and route.call_count == 2
