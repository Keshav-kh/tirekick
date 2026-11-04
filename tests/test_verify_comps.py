"""price_comps (B9) with mocked web-search responses: code-side filtering, stats, cache, failures."""

import json

import pytest

from tirekick import config
from tirekick.models import Listing
from tirekick.verify import comps as comps_mod
from tirekick.verify import muse
from tirekick.verify.comps import price_comps, summarize
from tirekick.verify.muse import Citation, SearchResult

L = Listing(listing_id="L", asking_price=9400, year=2015, make="Honda", model="Civic", trim="LX",
            mileage=84000, location="State College, PA")


def comp(price, url, cur="USD"):
    return {"price": price, "currency": cur, "url": url, "title": "t"}


def result(items, cited=("cars.com", "autotrader.com", "facebook.com", "kbb.com"), searched=True, text=None):
    body = text if text is not None else json.dumps({"comps": items})
    cites = [Citation(url=f"https://www.{h}/x", title=h) for h in cited]
    return SearchResult(text=body, citations=cites, searched=searched)


@pytest.fixture
def search(monkeypatch):
    monkeypatch.setenv("META_API_KEY", "test-key")
    calls = []

    def install(res=None, error=None):
        def fake(prompt, **kw):
            calls.append(prompt)
            if error:
                raise error
            return res
        monkeypatch.setattr(muse, "web_search", fake)
        return calls
    return install


GOOD = [comp(9000, "https://www.cars.com/a"), comp("$9,800", "https://www.autotrader.com/b"),
        comp(8500, "https://www.facebook.com/marketplace/item/1"), comp(10200, "https://www.kbb.com/honda/civic/2015/")]


def test_stats_computed_in_code_from_cited_prices(search):
    calls = search(result(GOOD))
    c = price_comps(L)
    assert (c.n, c.low, c.median, c.high) == (4, 8500, 9400, 10200)
    assert len(c.sources) == 4 and all(s.startswith("https://") for s in c.sources)
    assert "2015 Honda Civic LX" in calls[0] and "State College, PA" in calls[0] and "84,000 mi" in calls[0]


def test_numbers_without_url_or_uncited_host_or_implausible_are_dropped(search):
    items = GOOD[:3] + [
        comp(9100, None), comp(9100, "not a url"),                  # no URL
        comp(9300, "https://made-up-dealer.example/x"),             # host never cited
        comp(950, "https://www.cars.com/c"), comp(94000, "https://www.cars.com/d"),   # implausible
        comp(9000, "https://www.cars.com/a/"),                       # duplicate URL
        comp(34000, "https://www.cars.com/e", cur="AED"),            # wrong currency
    ]
    search(result(items))
    c = price_comps(L)
    assert c.n == 3 and c.median == 9000
    assert "no url" in c.note and "uncited" in c.note and "implausible" in c.note


def test_without_citations_any_url_bearing_comp_counts(search):
    search(result(GOOD, cited=()))
    assert price_comps(L).n == 4


def test_no_search_means_no_comps(search):
    search(result(GOOD, searched=False))
    c = price_comps(L)
    assert c.n == 0 and c.median is None and "without running a web search" in c.note


def test_fallback_reads_prices_from_cited_passages(search):
    text = "A 2015 Civic LX listed for $9,100 on Cars.com. Another sold for $9,700 on Autotrader."
    res = SearchResult(text=text, searched=True, citations=[
        Citation(url="https://www.cars.com/a", start_index=0, end_index=45),
        Citation(url="https://www.autotrader.com/b", start_index=47, end_index=len(text)),
    ])
    search(res)
    c = price_comps(L)
    assert (c.n, c.low, c.high) == (2, 9100, 9700) and "citations" in c.note


def test_cached_by_car_and_location(search):
    calls = search(result(GOOD))
    first = price_comps(L)
    again = price_comps(L.model_copy(update={"listing_id": "other", "asking_price": 9000}))
    assert first == again and len(calls) == 1
    assert list((config.DATA_DIR / "cache" / "comps").glob("*.json"))
    price_comps(L.model_copy(update={"location": "Dubai"}))
    assert len(calls) == 2


def test_empty_results_are_not_cached(search):
    calls = search(result([]))
    assert price_comps(L).n == 0
    price_comps(L)
    assert len(calls) == 2


def test_failures_never_raise(search, monkeypatch):
    search(error=muse.MuseError("400 web_search not enabled"))
    c = price_comps(L)
    assert c.n == 0 and "web search failed" in c.note
    monkeypatch.delenv("META_API_KEY")
    assert "no Meta Model API key" in price_comps(L.model_copy(update={"location": "Austin"})).note
    assert "year, make and model" in price_comps(Listing(listing_id="x", asking_price=1000)).note


def test_summarize_trims_outliers_from_low_high_only():
    assert summarize([]) == (None, None, None)
    assert summarize([9000, 8000]) == (8000, 8500, 9000)
    assert summarize([4000, 8800, 9000, 9200, 15000]) == (8800, 9000, 9200)


def test_comps_feed_policy_threshold(search):
    """check_offer accepts comps-backed reductions only with n >= 3; make sure n is the cited count."""
    search(result(GOOD[:2]))
    assert price_comps(L).n == 2
    assert comps_mod.MAX_COMPS == 8
