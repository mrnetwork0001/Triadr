import os
import sys
from pathlib import Path

import pytest

# Tests import the packages from the repo root, not an installed distribution.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_CREDENTIALS = ("GITHUB_TOKEN", "TELEGRAM_BOT_TOKEN", "SLACK_BOT_TOKEN", "STRIPE_SECRET_KEY",
                "TRIADR_ALLOW_LIVE_MONEY", "ANTHROPIC_API_KEY")


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch):
    """Unit tests must never turn an app LIVE or pick up operator defaults.

    A developer's .env is loaded by the entry points (and by importing the MCP
    stdio server), which would otherwise flip Stripe to LIVE inside the test
    process and send real requests from what should be pure unit tests. Every
    test starts with the credentials and TRIADR_* overrides cleared; the `live`
    fixture in test_live_paths.py sets its own throwaway values on top.
    """
    for var in _CREDENTIALS:
        monkeypatch.delenv(var, raising=False)
    for var in [v for v in os.environ if v.startswith("TRIADR_")]:
        monkeypatch.delenv(var, raising=False)
