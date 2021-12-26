import asyncio

import looptime


class MyEventLoop(asyncio.BaseEventLoop):
    pass


class ExtEventLoop(MyEventLoop):
    pass


class InheritedEventLoop(looptime.LoopTimeEventLoop, asyncio.BaseEventLoop):
    pass


def test_skipping_if_already_inherits_as_needed():
    cls = looptime.make_event_loop_class(InheritedEventLoop)
    assert cls is InheritedEventLoop


def test_class_creation_anew():
    cls = looptime.make_event_loop_class(MyEventLoop)
    assert issubclass(cls, MyEventLoop)
    assert issubclass(cls, looptime.LoopTimeEventLoop)
    assert cls.__name__ != MyEventLoop.__name__
    assert cls.__name__.startswith("Looptime")


def test_class_name_default():
    cls = looptime.make_event_loop_class(MyEventLoop)
    assert cls.__name__ == "LooptimeMyEventLoop"


def test_class_name_customized():
    cls = looptime.make_event_loop_class(MyEventLoop, prefix='Some')
    assert cls.__name__ == "SomeMyEventLoop"


def test_cache_hit_for_the_same_base_class():
    cls1 = looptime.make_event_loop_class(MyEventLoop)
    cls2 = looptime.make_event_loop_class(MyEventLoop)
    assert cls1 is cls2


def test_cache_miss_for_the_different_base_classes():
    cls1 = looptime.make_event_loop_class(MyEventLoop)
    cls2 = looptime.make_event_loop_class(ExtEventLoop)
    assert cls1 is not cls2
    assert not issubclass(cls1, cls2)
    assert not issubclass(cls2, cls1)
