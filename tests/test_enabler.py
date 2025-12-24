import asyncio
import sys

import pytest

import looptime


@pytest.mark.asyncio
async def test_enabler_as_context_manager():
    loop = asyncio.get_running_loop()
    enabled = isinstance(loop, looptime.LoopTimeEventLoop) and loop.looptime_on
    assert not enabled

    with looptime.enabled():
        enabled = isinstance(loop, looptime.LoopTimeEventLoop) and loop.looptime_on
    assert enabled


@pytest.mark.asyncio
async def test_enabler_as_decorator_for_sync_functions():
    @looptime.enabled()
    def fn(a: int) -> tuple[int, bool]:
        loop = asyncio.get_running_loop()
        enabled = isinstance(loop, looptime.LoopTimeEventLoop) and loop.looptime_on
        return a + 10, enabled

    loop = asyncio.get_running_loop()
    enabled = isinstance(loop, looptime.LoopTimeEventLoop) and loop.looptime_on
    assert not enabled

    result, enabled = fn(123)
    assert result == 133
    assert enabled


@pytest.mark.asyncio
async def test_enabler_as_decorator_for_async_functions():
    @looptime.enabled()
    async def fn(a: int) -> tuple[int, bool]:
        loop = asyncio.get_running_loop()
        enabled = isinstance(loop, looptime.LoopTimeEventLoop) and loop.looptime_on
        return a + 10, enabled

    loop = asyncio.get_running_loop()
    enabled = isinstance(loop, looptime.LoopTimeEventLoop) and loop.looptime_on
    assert not enabled

    result, enabled = await fn(123)
    assert result == 133
    assert enabled


@pytest.mark.skipif(sys.version_info < (3, 11), reason="Runners require Python>=3.11")
def test_enabler_with_explicit_loop():
    with asyncio.Runner() as runner:
        runner_loop = runner.get_loop()
        looptime.patch_event_loop(runner_loop, _enabled=False)
        with looptime.enabled(loop=runner_loop):
            enabled = isinstance(runner_loop, looptime.LoopTimeEventLoop) and runner_loop.looptime_on
    assert enabled


@pytest.mark.skipif(sys.version_info < (3, 11), reason="Runners require Python>=3.11")
def test_strict_mode_error():
    with asyncio.Runner() as runner:
        runner_loop = runner.get_loop()  # unpatched!
        with pytest.raises(RuntimeError, match="loop is not a looptime-patched loop"):
            with looptime.enabled(loop=runner_loop, strict=True):
                pass


@pytest.mark.skipif(sys.version_info < (3, 11), reason="Runners require Python>=3.11")
def test_nonstrict_mode_warning():
    with asyncio.Runner() as runner:
        runner_loop = runner.get_loop()  # unpatched!
        with pytest.warns(UserWarning, match="loop is not a looptime-patched loop"):
            with looptime.enabled(loop=runner_loop, strict=False):
                pass
