import asyncio
import time

import pytest

import looptime


def test_duration_is_none_initially():
    chronometer = looptime.Chronometer()
    assert chronometer.seconds is None


def test_duration_resets_on_reuse():
    chronometer = looptime.Chronometer()
    with chronometer:
        time.sleep(0.1)
    with chronometer:
        time.sleep(0.1)
    assert 0.1 <= chronometer.seconds <= 0.11


def test_conversion_to_int():
    chronometer = looptime.Chronometer()
    with chronometer:
        time.sleep(0.1)
    seconds = int(chronometer)
    assert seconds == 0


def test_conversion_to_float():
    chronometer = looptime.Chronometer()
    with chronometer:
        time.sleep(0.1)
    seconds = float(chronometer)
    assert 0.1 <= seconds < 0.11


@pytest.mark.asyncio
async def test_sync_context_manager():
    with looptime.Chronometer() as chronometer:
        time.sleep(0.1)
    assert 0.1 <= chronometer.seconds < 0.11


@pytest.mark.asyncio
async def test_async_context_manager():
    async with looptime.Chronometer() as chronometer:
        time.sleep(0.1)
    assert 0.1 <= chronometer.seconds < 0.11


@pytest.mark.asyncio
@pytest.mark.looptime(start=100)
async def test_readme_example(chronometer):
    event_loop = asyncio.get_running_loop()
    with chronometer, looptime.Chronometer(event_loop.time) as loopometer:
        await asyncio.sleep(1)
        await asyncio.sleep(1)
    assert chronometer.seconds < 0.01  # random code overhead
    assert loopometer.seconds == 2  # precise timing, no code overhead
    assert event_loop.time() == 102
