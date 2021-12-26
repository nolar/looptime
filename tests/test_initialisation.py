import asyncio

import looptime


class MyEventLoop(looptime.LoopTimeEventLoop, asyncio.SelectorEventLoop):
    pass


def test_initial_time_is_zero_by_default():
    loop = MyEventLoop()
    assert loop.time() == 0


def test_initial_time_is_customized():
    loop = MyEventLoop(start=123)
    assert loop.time() == 123


def test_double_init_patches_once():
    original_loop = asyncio.SelectorEventLoop()
    original_select = original_loop._selector.select

    looptime_loop = looptime.patch_event_loop(original_loop)
    patched_select_1 = looptime_loop._selector.select
    assert patched_select_1 is not original_select

    looptime_loop.setup_looptime()
    patched_select_2 = looptime_loop._selector.select
    assert patched_select_2 is not original_select
    assert patched_select_2 is patched_select_1
