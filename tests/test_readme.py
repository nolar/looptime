import asyncio

import async_timeout
import pytest


@pytest.mark.asyncio
@pytest.mark.looptime(end=1)
async def test_the_end_of_time(chronometer, looptime):
    with chronometer:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.Event().wait()
    assert looptime == 1
    assert chronometer >= 1


@pytest.mark.asyncio
@pytest.mark.looptime
async def test_async_timeout(chronometer, looptime):
    with chronometer:
        with pytest.raises(asyncio.TimeoutError):
            async with async_timeout.timeout(1):
                await asyncio.Event().wait()
    assert looptime == 1
    assert chronometer < 0.1
