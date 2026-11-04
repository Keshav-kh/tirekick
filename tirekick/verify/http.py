"""Small HTTP helper for the free NHTSA APIs: timeout + retry with backoff on 429/5xx. Owner: B."""

from __future__ import annotations

import time
from typing import Callable

import httpx

BACKOFF_S = (1.0, 2.0, 4.0)
_sleep: Callable[[float], None] = time.sleep  # tests monkeypatch this


def get_json(url: str, params: dict | None = None, timeout: float = 10.0) -> dict:
    """GET and parse JSON. Retries 429 / 5xx / transport errors (1 s, 2 s, 4 s); raises otherwise."""
    last: Exception | None = None
    for attempt in range(len(BACKOFF_S) + 1):
        try:
            resp = httpx.get(url, params=params, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            last = e
            if e.response.status_code != 429 and e.response.status_code < 500:
                raise
        except httpx.TransportError as e:
            last = e
        if attempt < len(BACKOFF_S):
            _sleep(BACKOFF_S[attempt])
    raise last  # type: ignore[misc]
