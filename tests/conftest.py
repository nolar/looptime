import asyncio

import pytest

import looptime


@pytest.fixture(autouse=True)
def _clear_caches():
    looptime.reset_caches()
    yield
    looptime.reset_caches()


@pytest.fixture()
def looptime_loop():
    return looptime.patch_event_loop(asyncio.new_event_loop())
