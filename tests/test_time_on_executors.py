import asyncio
import time


def test_with_empty_code(chronometer, looptime_loop):
    looptime_loop.setup_looptime(idle_step=0.01)

    def sync():
        pass

    async def f():
        await asyncio.get_running_loop().run_in_executor(None, sync)

    with chronometer:
        looptime_loop.run_until_complete(f())
    assert looptime_loop.time() == 0.0  # possibly 0.01 if the thread spawns too slowly
    assert 0.0 <= chronometer.seconds < 0.1


def test_with_sleep(chronometer, looptime_loop):
    looptime_loop.setup_looptime(idle_step=0.01)

    def sync():
        time.sleep(0.1)

    async def f():
        await asyncio.get_running_loop().run_in_executor(None, sync)

    with chronometer:
        looptime_loop.run_until_complete(f())
    assert looptime_loop.time() == 0.1  # possibly 0.11 if the threads spawns too slowly
    assert 0.1 <= chronometer.seconds < 0.11
