import asyncio
import time
import warnings

import async_timeout
import pytest

import looptime


async def _make_event() -> asyncio.Event:
    """Create an event attached to a proper event loop."""
    return asyncio.Event()


def test_initial_time_is_zero_by_default(looptime_loop):
    assert looptime_loop.time() == 0


def test_initial_time_is_customized(looptime_loop):
    looptime_loop.setup_looptime(start=123)
    assert looptime_loop.time() == 123


def test_execution_takes_near_zero_time(chronometer, looptime_loop):
    with chronometer:
        looptime_loop.run_until_complete(asyncio.sleep(10))
    assert looptime_loop.time() == 10
    assert 0.0 <= chronometer.seconds < 0.01


def test_execution_takes_true_time_when_disabled(chronometer, looptime_loop):
    looptime_loop.setup_looptime(_enabled=False)
    with chronometer:
        looptime_loop.run_until_complete(asyncio.sleep(1))
    assert looptime_loop.time() == 1
    assert 1 <= chronometer.seconds < 1.1


def test_real_time_is_ignored(chronometer, looptime_loop):
    async def f():
        await asyncio.sleep(5)
        time.sleep(0.1)
        await asyncio.sleep(5)

    with chronometer:
        looptime_loop.run_until_complete(f())
    assert looptime_loop.time() == 10
    assert 0.1 <= chronometer.seconds < 0.12


def test_timeout_doesnt_happen_before_entered_the_code(chronometer, looptime_loop):
    async def f():
        async with async_timeout.timeout(10):
            await asyncio.sleep(1)

    with chronometer:
        looptime_loop.run_until_complete(f())
    assert looptime_loop.time() == 1
    assert 0.0 <= chronometer.seconds < 0.01


def test_timeout_does_happen_according_to_schedule(chronometer, looptime_loop):
    async def f():
        async with async_timeout.timeout(1):
            await asyncio.sleep(10)

    with chronometer:
        with pytest.raises(asyncio.TimeoutError):
            looptime_loop.run_until_complete(f())
    assert looptime_loop.time() == 1
    assert 0.0 <= chronometer.seconds < 0.01


def test_end_of_time_reached(chronometer, looptime_loop):
    looptime_loop.setup_looptime(end=1)

    async def f():
        await asyncio.sleep(10)

    with chronometer:
        with pytest.raises(looptime.LoopTimeoutError):
            looptime_loop.run_until_complete(f())
    assert looptime_loop.time() == 1
    assert 0.0 <= chronometer.seconds < 0.01


def test_end_of_time_injects_into_coros(looptime_loop):
    looptime_loop.setup_looptime(end=1)
    exc = None

    async def f():
        nonlocal exc
        try:
            await asyncio.sleep(10)
        except Exception as e:
            exc = e

    looptime_loop.run_until_complete(f())
    assert isinstance(exc, looptime.LoopTimeoutError)


def test_end_of_time_allows_zerotime_finalizers(looptime_loop):
    looptime_loop.setup_looptime(end=1)
    with pytest.raises(looptime.LoopTimeoutError):
        looptime_loop.run_until_complete(asyncio.sleep(1))

    some_event = looptime_loop.run_until_complete(_make_event())
    some_event.set()
    looptime_loop.run_until_complete(asyncio.sleep(0))
    looptime_loop.run_until_complete(some_event.wait())


def test_end_of_time_cancels_realtime_finalizers(looptime_loop):
    looptime_loop.setup_looptime(end=1)
    with pytest.raises(looptime.LoopTimeoutError):
        looptime_loop.run_until_complete(asyncio.sleep(1))

    some_event = looptime_loop.run_until_complete(_make_event())
    with pytest.raises(looptime.LoopTimeoutError):
        looptime_loop.run_until_complete(asyncio.sleep(0.1))
    with pytest.raises(looptime.LoopTimeoutError):
        looptime_loop.run_until_complete(some_event.wait())


@pytest.mark.parametrize('start, sleep, expected_time', [
    (0.2, 0.09, 0.29),  # in Python: 0.29000000000000004
    (0.2, 0.21, 0.41),  # in Python: 0.41000000000000003
])
def test_floating_point_precision_fixed(looptime_loop, start, sleep, expected_time):
    looptime_loop.setup_looptime(start=start)

    async def f():
        await asyncio.sleep(sleep)

    looptime_loop.run_until_complete(f())
    assert looptime_loop.time() == expected_time


def test_repeated_setup_keeps_the_time(looptime_loop):
    looptime_loop.setup_looptime(start=123)
    looptime_loop.setup_looptime()
    assert looptime_loop.time() == 123  # not zero


def test_forward_time_moves_works(looptime_loop):
    looptime_loop.setup_looptime(start=123)
    looptime_loop.setup_looptime(start=456)
    assert looptime_loop.time() == 456


def test_backward_time_moves_warns(looptime_loop):
    looptime_loop.setup_looptime(start=456)
    with pytest.warns(looptime.TimeWarning, match=r"from 456.0 to 123.0"):
        looptime_loop.setup_looptime(start=123)
    assert looptime_loop.time() == 123  # modified


def test_backward_time_moves_raises_and_keeps_the_time(looptime_loop):
    looptime_loop.setup_looptime(start=456)
    with pytest.raises(looptime.TimeWarning):
        with warnings.catch_warnings():
            warnings.filterwarnings('error', category=looptime.TimeWarning)
            looptime_loop.setup_looptime(start=123)
    assert looptime_loop.time() == 456  # unmodified
