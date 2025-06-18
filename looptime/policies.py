import asyncio
from typing import Callable, Any, Type, cast

from looptime import loops, patchers


# TODO: BaseDefaultEventLoopPolicy or AbstractDefaultEventLoopPolicy for a mixin?
class LoopTimeEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    """
    A mixin to inject into event loop policies to make them looptime-enabled.

    This policy mixin ensures that all event loops produced are either already
    looptime-enabled (i.e. inherit from :class:`LoopTimeEventLoop`),
    or it monkey-patches the newly produced event loops to be looptime-enabled.

    This mixin can be used explicitly when defining the custom policy classes.
    It is used implicitly when monkey-patching the existing policies when
    enforcing the looptime capabilities in tests with pytest-asyncio>=1.0.0.

    For monkey-patching, a new empty (no-member) class is created at runtime,
    with tis mixin and the original policy class as the bases, and is injected
    into the policy's instance ``__class__`` attribute.
    """

    # Precisely the args/kwargs as in the LoopTimeEventLoop's constructor.
    # Args/kwargs are passed through in case this class is used as a mixin.
    def __init__(
            self,
            *args: Any,
            start: float | None | Callable[[], float | None] = None,
            end: float | None | Callable[[], float | None] = None,
            resolution: float = 1e-6,  # to cut off the floating-point errors
            idle_step: float | None = None,
            idle_timeout: float | None = None,
            noop_cycles: int = 42,
            **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.setup_looptime(
            start=start,
            end=end,
            resolution=resolution,
            idle_step=idle_step,
            idle_timeout=idle_timeout,
            noop_cycles=noop_cycles,
        )

    def setup_looptime(
            self,
            *,
            start: float | None | Callable[[], float | None] = None,
            end: float | None | Callable[[], float | None] = None,
            resolution: float = 1e-6,  # to cut off the floating-point errors
            idle_step: float | None = None,
            idle_timeout: float | None = None,
            noop_cycles: int = 42,
    ) -> None:
        self.__start = start
        self.__end = end
        self.__resolution = resolution
        self.__idle_step = idle_step
        self.__idle_timeout = idle_timeout
        self.__noop_cycles = noop_cycles

    # TODO: which method?
    # def get_event_loop(self) -> loops.LoopTimeEventLoop:
    def new_event_loop(self) -> loops.LoopTimeEventLoop:
        # loop = super().get_event_loop()
        loop = super().new_event_loop()
        return patchers.patch_event_loop(
            loop,
            start=self.__start,
            end=self.__end,
            resolution=self.__resolution,
            idle_step=self.__idle_step,
            idle_timeout=self.__idle_timeout,
            noop_cycles=self.__noop_cycles,
        )


_policies_cache: dict[Type[asyncio.AbstractEventLoopPolicy], Type[LoopTimeEventLoopPolicy]] = {}


def make_event_loop_policy_class(
        cls: Type[asyncio.AbstractEventLoopPolicy],
        *,
        prefix: str = 'Looptime',
) -> type[LoopTimeEventLoopPolicy]:
    if issubclass(cls, LoopTimeEventLoopPolicy):
        return cls
    elif cls not in _policies_cache:
        new_class = type(f'{prefix}{cls.__name__}', (LoopTimeEventLoopPolicy, cls), {})
        _policies_cache[cls] = new_class
    return _policies_cache[cls]


def patch_event_loop_policy(
        policy: asyncio.AbstractEventLoopPolicy,
        **kwargs: Any,
) -> LoopTimeEventLoopPolicy:
    """
    Convert any pre-existing event loop policy to be looptime-enabled.
    """
    result: loops.LoopTimeEventLoop
    if isinstance(policy, LoopTimeEventLoopPolicy):
        return policy
    else:
        new_class: type[LoopTimeEventLoopPolicy] = make_event_loop_policy_class(policy.__class__)
        policy.__class__ = new_class
        policy = cast(LoopTimeEventLoopPolicy, policy)
        policy.setup_looptime(**kwargs)
        return policy
