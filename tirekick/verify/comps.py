"""price_comps: comparable prices via Muse Spark web search, with citations. Owner: B.

TODO(B, Tue): call Muse Spark with its built-in web_search tool (Meta's Responses API; check
dev.meta.ai for the exact tool syntax). Ask for 3-8 comparable private-party prices for the same
year/make/model/trim and similar mileage near listing.location, each with its source URL.
Compute low/median/high in code from the cited numbers only. Cache by (year, make, model, trim, location).
"""

from __future__ import annotations

from tirekick.models import Listing, PriceComps


def price_comps(listing: Listing) -> PriceComps:
    return PriceComps(currency=listing.currency, note="comps not implemented yet")
