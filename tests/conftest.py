"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_cancelled_devices():
    """Clear the global cancellation set so cancel state can't leak across tests.

    ``imouse_farm.actions.cancel`` keeps a module-level set; tests that exercise
    stop/kill paths (e.g. farm batch) otherwise leave device ids marked cancelled,
    which makes later watcher checks early-return.
    """
    from imouse_farm.actions import cancel

    cancel._cancelled_devices.clear()
    yield
    cancel._cancelled_devices.clear()
