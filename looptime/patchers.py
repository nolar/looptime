from __future__ import annotations

import asyncio
from typing import Any, Type, cast

from looptime import loops

_class_cache: dict[Type[asyncio.BaseEventLoop], Type[loops.LoopTimeEventLoop]] = {}


def reset_caches() -> None:
    _class_cache.clear()


def make_event_loop_class(
        cls: Type[asyncio.BaseEventLoop],
        *,
        prefix: str = 'Looptime',
) -> Type[loops.LoopTimeEventLoop]:
    if issubclass(cls, loops.LoopTimeEventLoop):
        return cls
    elif cls not in _class_cache:
        new_class = type(f'{prefix}{cls.__name__}', (loops.LoopTimeEventLoop, cls), {})
        _class_cache[cls] = new_class
    return _class_cache[cls]


def patch_event_loop(
        loop: asyncio.BaseEventLoop,
        **kwargs: Any,
) -> loops.LoopTimeEventLoop:
    result: loops.LoopTimeEventLoop
    match loop:
        case loops.LoopTimeEventLoop():
            return loop
        case _:
            new_class = make_event_loop_class(loop.__class__)
            loop.__class__ = new_class
            loop = cast(loops.LoopTimeEventLoop, loop)
            loop.setup_looptime(**kwargs)
            return loop


def new_event_loop(**kwargs: Any) -> loops.LoopTimeEventLoop:
    return patch_event_loop(cast(asyncio.BaseEventLoop, asyncio.new_event_loop()), **kwargs)
