from __future__ import annotations

import asyncio
from typing import Any, Type, cast

from . import loops

_class_cache: dict[Type[asyncio.BaseEventLoop], Type[loops.LoopTimeEventLoop]] = {}


def reset_caches() -> None:
    """
    Purge all caches populated by the patching function of ``looptime``.

    The classes themselves are not destroyed, so if there are event loops
    that were created before the caches are cleared, they will continue to work.
    """
    _class_cache.clear()


def make_event_loop_class(
        cls: Type[asyncio.BaseEventLoop],
        *,
        prefix: str = 'Looptime',
) -> Type[loops.LoopTimeEventLoop]:
    """
    Create a new looptime-enabled event loop class from the original class.

    Technically, it is equivalent to creating a new class that inherits
    from the original class and :class:`looptime.LoopTimeEventLoop` as a mixin,
    with no content (methods or fields) of its own:

    .. code-block:: python

        # Not the actual code, just the idea of what happens under the hood.
        class NewEventLoop(loops.LoopTimeEventLoop, cls):
            pass

    New classes are cached, so the same original class always produces the same
    derived class, not a new one on every call.
    """
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
    """
    Patch an existing event loop to be looptime-ready.

    This operation is idempotent and can be safely called multiple times.

    Internally, it takes the existing class of the event loop and replaces it
    with the new class, which is a mix of the original class and
    :class:`looptime.LoopTimeEventLoop` as a mixin. The new classes are cached.
    """
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
    """
    Create a new event loop as :func:`asyncio.new_event_loop`, but patched.
    """
    return patch_event_loop(cast(asyncio.BaseEventLoop, asyncio.new_event_loop()), **kwargs)
