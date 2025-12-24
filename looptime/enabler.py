import asyncio
import functools
import inspect
import warnings
from typing import Any, Callable, ContextManager, ParamSpec, TypeVar

from looptime import loops

P = ParamSpec('P')
R = TypeVar('R')


class enabled(ContextManager[None]):
    """
    Enable the looptime time compaction temporarily.

    If used as a context manager, enables the time compaction for the wrapped
    code block only::

        import asyncio
        import looptime

        async def main() -> None:
            with looptime.enabled(strict=True):
                await asyncio.sleep(10)

        if __name__ == '__main__':
            asuncio.run(main())

    If used as a function/fixture decorator, enables the time compaction
    for the duration of the function/fixture::

        import asyncio
        import looptime

        @looptime.enabled(strict=True)
        async def main() -> None:
            await asyncio.sleep(10)

        if __name__ == '__main__':
            asuncio.run(main())

    In both cases, the event loop must be pre-patched (usually at creation).
    In strict mode, if the event loop is not patched, the call will fail.
    In non-strict mode (the default), it will issue a warning and continue
    with the real time flow (i.e. with no time compaction).

    Use it, for example, for fixtures or finalizers of fixtures where the fast
    time flow is required despite fixtures are normally excluded from the time
    compaction magic (because it is impossible or difficult to infer which
    event loop is being used in the multi-scoped setup of pytest-asyncio),
    and because of the structure of pytest hooks for fixture finalizing
    (no finalizer hook, only the post-finalizer hook, when it is too late).

    Beware of a caveat: if used as a decorator on a yield-based fixture,
    it will enable the looptime magic for the whole duration of the test,
    including all its fixtures (even undecorated ones), until the decorated
    fixture reaches its finalizer. This might have unexpected side effects.
    """
    strict: bool
    _loop: asyncio.AbstractEventLoop | None
    _mgr: ContextManager[None] | None

    def __init__(self, *, strict: bool = False, loop: asyncio.AbstractEventLoop | None = None) -> None:
        super().__init__()
        self.strict = strict
        self._loop = loop
        self._mgr = None

    def __enter__(self) -> None:
        msg = "The running loop is not a looptime-patched loop, cannot enable it."
        loop = self._loop if self._loop is not None else asyncio.get_running_loop()
        if isinstance(loop, loops.LoopTimeEventLoop):
            self._mgr = loop.looptime_enabled()
            self._mgr.__enter__()
        elif self.strict:
            raise RuntimeError(msg)
        else:
            warnings.warn(msg, UserWarning)

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._mgr is not None:
            self._mgr.__exit__(exc_type, exc_val, exc_tb)
            self._mgr = None

    # Type checkers: too complicated. We get R=Coroutine[Y,S,RR] for async functions,
    # but return that last RR part, which turns to be Any. The runtime is unaffected.
    # I don't know how to properly annotate such a mixed sync-async decorator internally.
    # The external declaration of __call__() is sufficient and correct.
    # TODO: LATER: try annotating it properly.
    def __call__(self, fn: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                nonlocal self
                with self:
                    return await fn(*args, **kwargs)  # type: ignore
        else:
            @functools.wraps(fn)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                nonlocal self
                with self:
                    return fn(*args, **kwargs)

        return wrapper # type: ignore
