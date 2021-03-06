import asyncio

import looptime


class MyEventLoop(asyncio.SelectorEventLoop):
    pass


class InheritedEventLoop(looptime.LoopTimeEventLoop, asyncio.SelectorEventLoop):
    pass


def test_patching_skipped_if_already_inherited():
    old_loop = InheritedEventLoop()
    new_loop = looptime.patch_event_loop(old_loop)
    assert old_loop is new_loop


def test_patching_injects_the_base_class():
    old_loop = MyEventLoop()
    new_loop = looptime.patch_event_loop(old_loop)
    assert old_loop is new_loop
    assert isinstance(new_loop, MyEventLoop)
    assert isinstance(new_loop, looptime.LoopTimeEventLoop)


def test_patching_initialises():
    old_loop = MyEventLoop()
    new_loop = looptime.patch_event_loop(old_loop)
    assert hasattr(new_loop, '_LoopTimeEventLoop__now')


def test_initial_time_is_customized():
    loop = looptime.patch_event_loop(asyncio.new_event_loop(), start=123)
    assert loop.time() == 123


def test_new_event_loop_is_patched_out_of_the_box():
    default_loop_cls = asyncio.new_event_loop().__class__
    loop = looptime.new_event_loop(start=123)
    assert isinstance(loop, default_loop_cls)
    assert isinstance(loop, looptime.LoopTimeEventLoop)
    assert loop.time() == 123
