"""Environment-driven settings. Read at call time so tests can monkeypatch env vars."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("TIREKICK_DATA_DIR", "data"))


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def flag(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in {"1", "true", "yes", "on"}


def fake_ai() -> bool:
    return flag("TIREKICK_FAKE_AI")


def dev_mode() -> bool:
    return flag("TIREKICK_DEV")


def data_path(*parts: str) -> Path:
    p = DATA_DIR.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
