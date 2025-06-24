from __future__ import annotations

import asyncio
import contextlib
import selectors
import time
import warnings
import weakref
from typing import TYPE_CHECKING, Any, Callable, Iterator, MutableSet, TypeVar, cast, overload

_T = TypeVar('_T')

if TYPE_CHECKING:
    AnyFuture = asyncio.Future[Any]
    AnyTask = asyncio.Task[Any]
else:
    AnyFuture = asyncio.Future
    AnyTask = asyncio.Task


class TimeWarning(UserWarning):
    """Issued when the loop time moves backwards, violating its monotonicity."""
    pass


class LoopTimeoutError(asyncio.TimeoutError):
    """A special kind of timeout when the loop's time reaches its end."""
    pass


class IdleTimeoutError(asyncio.TimeoutError):
    """A special kind of timeout when the loop idles with no external I/O."""
    pass


class LoopTimeEventLoop(asyncio.BaseEventLoop):

    # BaseEventLoop does not have "_selector" declared but uses it in _run_once().
    _selector: selectors.BaseSelector

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
            _enabled: bool | None = None,  # None means do nothing
    ) -> None:
        """
        Set all the fake-time fields and patch the i/o selector.

        This is the same as ``__init__(...)``, except that it can be used
        when the mixin/class is injected into the existing event loop object.
        In that case, the object is already initialised except for these fields.
        """
        new_time: float | None = start() if callable(start) else start
        end_time: float | None = end() if callable(end) else end
        old_time: float | None
        try:
            # NB: using the existing (old) reciprocal!
            old_time = self.__int2time(self.__now)
        except AttributeError:  # initial setup: either reciprocals or __now are absent
            old_time = None
        new_time = float(new_time) if new_time is not None else None

        # If it is the 2nd or later setup, double-check on time monotonicity.
        # In some configurations, this waring might raise an error and fail the test.
        # In that case, the time must not be changed for the next test.
        if old_time is not None and new_time is not None and new_time < old_time:
            warnings.warn(
                f"The time of the event loop moves backwards from {old_time} to {new_time},"
                " thus breaking the monotonicity of time. This is dangerous!"
                " Perhaps, caused by reusing a higher-scope event loop in tests."
                " Revise the scopes of fixtures & event loops."
                " Remove the start=… kwarg and rely on arbitrary time values."
                " Migrate from `loop.time()` to the `looptime` numeric fixture.",
                TimeWarning,
            )

        self.__resolution_reciprocal: int = round(1/resolution)
        self.__now: int = self.__time2int(new_time or old_time) or 0
        self.__end: int | None = self.__time2int(end_time)

        self.__idle_timeout: int | None = self.__time2int(idle_timeout)
        self.__idle_step: int | None = self.__time2int(idle_step)
        self.__idle_end: int | None = None

        self.__noop_limit: int | None = None
        self.__noop_cycle: int | None = None
        self.__noop_cycles: int = noop_cycles

        self.__sync_futures: MutableSet[AnyFuture] = weakref.WeakSet()
        self.__sync_clock: Callable[[], float] = time.perf_counter
        self.__sync_ts: float | None = None  # system/true-time clock timestamp

        try:
            self.__enabled  # type: ignore
        except AttributeError:
            self.__enabled = _enabled if _enabled is not None else True  # old behaviour
        else:
            self.__enabled = _enabled if _enabled is not None else self.__enabled

        # TODO: why do we patch the selector as an object while the event loop as a class?
        #       this should be the same patching method for both.
        try:
            self.__original_select  # type: ignore
        except AttributeError:
            self.__original_select = self._selector.select
            self._selector.select = self.__replaced_select  # type: ignore

    @property
    def looptime_on(self) -> bool:
        return bool(self.__enabled)

    @contextlib.contextmanager
    def looptime_enabled(self) -> Iterator[None]:
        """
        Temporarily enable the time compaction, restore the normal mode on exit.
        """
        if self.__enabled:
            raise RuntimeError('Looptime mode is already enabled. Entered twice? Avoid this!')
        old_enabled = self.__enabled
        self.__enabled = True
        try:
            yield
        finally:
            self.__enabled = old_enabled

    def time(self) -> float:
        return self.__int2time(self.__now)

    def run_in_executor(self, executor: Any, func: Any, *args: Any) -> AnyFuture:  # type: ignore
        future = super().run_in_executor(executor, func, *args)
        if isinstance(future, asyncio.Future):
            self.__sync_futures.add(future)
        return future

    def __replaced_select(self, timeout: float | None) -> list[tuple[Any, Any]]:
        overtime = False

        # First of all, do the i/o polling. Some i/o has happened? Fine! Process it asap!
        # The time-play starts only when there is nothing to process from the outside (i.e. no i/o).
        ready: list[tuple[Any, Any]] = self.__original_select(timeout=0)
        if ready:
            pass

        # If nothing to do right now, and the time is not compacted, truly sleep as requested.
        # Move the fake time by the exact real time spent in this wait (±discrepancies).
        elif not self.__enabled:
            t0 = time.monotonic()
            ready = self.__original_select(timeout=timeout)
            t1 = time.monotonic()

            # If timeout=None, it never exists until ready. This timeout check is for typing only.
            self.__now += self.__time2int(t1 - t0 if ready or timeout is None else timeout)

        # Regardless of the timeout, if there are executors sync futures, we move the time in steps.
        # The timeout (if present) can limit the size of the step, but not the logic of stepping.
        # Generally, external things (threads) take some time (e.g. for thread spawning).
        # We cannot reliably hook into the abstract executors or their sync futures,
        # so we have to spend the true-time waiting for them.
        # We hope that they finish fast enough —in a few steps— and schedule their new handles.
        elif any(not fut.done() for fut in self.__sync_futures):
            self.__noop_limit = self.__noop_cycle = None

            # Unbalanced split: if the events arrive closer to the end, still move the loop time.
            # But skip the loop time increment if the events arrive early (first 80% of the range).
            timeout, step, overtime = self.__sync(timeout, self.__idle_step)
            readyA = self.__original_select(timeout=timeout * 0.8 if timeout is not None else None)
            readyB = self.__original_select(timeout=timeout * 0.2 if timeout is not None else None)
            ready = readyA + readyB
            self.__now += step if not readyA else 0

        # There is nothing to run or to wait inside the loop, only the external actors (I/O)
        # can put life into the loop: either via the regular I/O (e.g. sockets, servers, files),
        # or via a dummy self-writing socket of the event loop (used by the "thread-safe" calls).
        # Instead of the eternal sleep, limit it to little true-time steps until the end-of-time.
        # Set to `None` to actually sleep to infinity. Set to `0` to only poll and fail instantly.
        elif timeout is None:
            if self.__idle_end is None and self.__idle_timeout is not None:
                self.__idle_end = self.__now + self.__idle_timeout

            # Unbalanced split: if the events arrive closer to the end, still move the loop time.
            # But skip the loop time increment if the events arrive early (first 80% of the range).
            timeout, step, overtime = self.__sync(timeout, self.__idle_step, self.__idle_end)
            readyA = self.__original_select(timeout=timeout * 0.8 if timeout is not None else None)
            readyB = self.__original_select(timeout=timeout * 0.2 if timeout is not None else None)
            ready = readyA + readyB
            self.__now += step if not readyA else 0

        # There are handles ready to be executed right now. The time never advances here.
        # We are explicitly asked to quick-check (poll) the status of I/O sockets just in case.
        # Note: the countdown should execute for N cycles strictly in the loop's no-op mode,
        # so any i/o polling resets the cycle counter.
        elif timeout == 0:
            if self.__noop_limit is not None:
                self.__noop_cycle = 0

        # Now, we have a request to actually move the time to the next scheduled timer/handle.
        # Instead, we initiate a no-op cycle to let the coros/tasks/context-managers/generators run.
        # Without this no-op cycle, consecutive async/await operations sometimes have no chance
        # to execute because the earlier operations set a timeout or schedule the timer-handles
        # so that the fake-time moves before it gets to the next operations. For example:
        #       async with async_timeout.timeout(2):  # schedules to T0+2s, shifts the time, raises.
        #           await asyncio.sleep(1)            # gets no chance to set its handle to T0+1s.
        elif self.__noop_limit is None or self.__noop_cycle is None:
            self.__noop_limit = self.__noop_cycles
            self.__noop_cycle = 0

        # Regardless of the requested timeout, let the no-op cycle go without side effects.
        # We never sleep or advance the loop time while in this cycle-throttling mode.
        elif self.__noop_cycle < self.__noop_limit:
            self.__noop_cycle += 1

        # Finally, the no-op cycles are over. We move the fake clock to the next scheduled handle!
        # Since there is nothing that can happen from the outside, move the time all at once.
        # Moving it in smaller steps can be a waste of compute power (though, not harmful).
        else:
            _, step, overtime = self.__sync(timeout)
            self.__noop_limit = self.__noop_cycle = None
            self.__now += step

        # If any i/o has happened, we've got work to do: all idling countdowns should restart anew.
        if ready:
            self.__idle_end = None
            self.__noop_limit = None
            self.__noop_cycle = None

        task: AnyTask
        future: AnyFuture

        # If the loop has reached its end-of-time, destroy the loop's universe: stop all its tasks.
        # If possible, inject the descriptive exceptions; if not, just cancel them (on every cycle).
        if overtime and self.__end is not None and self.__now >= self.__end:
            for task in asyncio.all_tasks():
                future = cast(AnyFuture, getattr(task, '_fut_waiter', None))
                if future is not None:
                    future.set_exception(LoopTimeoutError(
                        "The event loop has reached its end-of-time. "
                        "All running tasks are considered timed out."))
                else:
                    task.cancel()

        # If the end-of-time is not reached yet, but the loop is idling for too long? Fail too.
        if overtime and self.__idle_end is not None and self.__now >= self.__idle_end:
            for task in asyncio.all_tasks():
                future = cast(AnyFuture, getattr(task, '_fut_waiter', None))
                if future is not None:
                    future.set_exception(IdleTimeoutError(
                        "The event loop was idle for too long — giving up on waiting for new i/o. "
                        "All running tasks are considered timed out."))
                else:
                    task.cancel()

        return ready

    def __sync(
            self,
            timeout: float | None,
            step: int | None = None,
            end: int | None = None,
    ) -> tuple[float | None, int, bool]:
        """
        Synchronise the loop-time and real-time steps as much as possible.

        In some cases, the loop time moves in sync with the real-world time:
        specifically, when there is nothing inside the loop that can
        fast-forward the loop time and only external occasions can move it.
        (The "external occasions" are either i/o or synchronous executors.)

        The loop time moves in sharp steps. However, there is also code overhead
        that consumes time between the steps, making the loop time misaligned
        with the real time.

        To work around that, the we keep track of the timestamps when the last
        sync happened and adjusts the real-clock timeout and loop-time step.
        For example, in a sequence of 4x loop-time steps of 0.01 seconds,
        the code overhead between steps can be 0.0013, 0.0011, 0.0015 seconds;
        in that case, the sleeps will be 0.01, 0.0087, 0.0089, 0.0085 seconds.

        This implementation is sufficiently precise but not very precise —
        it measures the time from one sync to another, but not for the whole
        sequence of steps.
        """
        overtime = False

        # Move the loop time precisely to the nearest planned event, not beyond it.
        real_step: int | None = step
        if timeout is not None:
            if real_step is not None:
                real_step = min(real_step, self.__time2int(timeout))
            else:
                real_step = self.__time2int(timeout)
        if end is not None:
            if real_step is not None:
                overtime = real_step >= end - self.__now
                real_step = min(real_step, end - self.__now)
            else:
                overtime = True
                real_step = end - self.__now
        if self.__end is not None:
            if real_step is not None:
                overtime = real_step >= self.__end - self.__now
                real_step = min(real_step, self.__end - self.__now)
            else:
                overtime = True
                real_step = self.__end - self.__now

        # Normally, the real-clock step is the same as the loop-time step.
        real_timeout = self.__int2time(real_step)

        # Optionally, adjust the real-clock sleep by the code overhead since the last time sync.
        # The code overhead timedelta can be negative if the previous cycle was interrupted by i/o.
        prev_ts = self.__sync_ts
        curr_ts = self.__sync_ts = self.__sync_clock()
        if real_timeout is not None and prev_ts is not None and curr_ts > prev_ts:
            code_overhead = curr_ts - prev_ts
            real_timeout = max(0.0, real_timeout - code_overhead)

        # Pre-allocate the time for the calculated timeout (assuming the timeout is fully used).
        if real_timeout is not None:
            self.__sync_ts += real_timeout

        # Make the steps easier for int math: use 0 instead of None for "no step".
        return real_timeout, (real_step or 0), overtime

    @overload
    def __time2int(self, time: float) -> int: ...

    @overload
    def __time2int(self, time: None) -> None: ...

    def __time2int(self, time: float | None) -> int | None:
        """
        Convert the supposed time in seconds to its INTernal INTeger form.

        All time math is done in integers to avoid floating point errors
        (there can also be some performance gain, but this is not the goal).

        Otherwise, the time assertions fail easily because of this::

            0.2-0.05 == 0.15000000000000002
            0.2-0.19 == 0.010000000000000009
            0.2+0.21 == 0.41000000000000003
        """
        return None if time is None else round(time * self.__resolution_reciprocal)

    @overload
    def __int2time(self, time: int) -> float: ...

    @overload
    def __int2time(self, time: None) -> None: ...

    def __int2time(self, time: int | None) -> float | None:
        """
        Convert the INTernal INTeger form of time back to the time in seconds.

        The int/int division is better than the int*float multiplication::

            100_000 * 0.000_001 == 0.09999999999999999
            100_000 / round(1/0.000_001) == 0.1
        """
        return None if time is None else time / self.__resolution_reciprocal
