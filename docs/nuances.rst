=======
Nuances
=======

Premature finalization
======================

Consider this test:

.. code-block:: python

    import asyncio
    import async_timeout
    import pytest


    @pytest.mark.asyncio
    @pytest.mark.looptime
    async def test_me():
        async with async_timeout.timeout(9):
            await asyncio.sleep(1)

Normally, it should not fail. However, with fake time (without workarounds),
the following step-by-step scenario is possible:

* ``async_timeout`` library sets its delayed timer at 9 seconds from now.
* The event loop notices that there is only one timer at T0+9s.
* The event loop fast-forwards time to ``9``.
* Since there are no other handles/timers, that timer is executed.
* ``async_timeout`` fails the test with ``asyncio.TimeoutError``.
* The ``sleep()`` never gets any chance to be scheduled or executed.

To solve this, ``looptime`` performs several dummy zero-time no-op cycles
before actually moving the time forward. This gives other coroutines,
tasks, and handles a fair chance to be entered, spawned, and scheduled.
This is why the example works as intended.

The ``noop_cycles`` (``int``) setting is how many cycles the event loop makes.
The default is ``42``. Why 42? Well, why not, indeed.


Sync-async synchronization
==========================

Consider this test, which mixes sync & async activities & primitives:

.. code-block:: python

    import asyncio
    import async_timeout
    import contextlib
    import pytest
    import threading


    def sync_fn(event: threading.Event):
        event.set()


    @pytest.mark.asyncio
    @pytest.mark.looptime
    async def test_me(event_loop):
        sync_event = threading.Event()
        with contextlib.suppress(asyncio.TimeoutError):
            async with async_timeout.timeout(9):
                await event_loop.run_in_executor(None, sync_fn, sync_event)
        assert sync_event.is_set()

With true time, this test will finish in a fraction of a second.
However, with fake time (with no workarounds), the following happens:

* A new synchronous event is created; it is unset by default.
* A synchronous task is submitted to a thread pool executor.
* The thread pool starts spawning a new thread and passing the task there.
* An asynchronous awaitable (future) is returned, which is chained
  with its synchronous counterpart.
* ``looptime`` performs its no-op cycles, letting all coroutines start,
  but it does this in near-zero true-time.
* The event loop forwards its time to 9 seconds and raises a timeout error.
* The test suppresses the timeout, checks the assertion, and fails:
  the sync event is still unset.
* A fraction of a second (e.g., ``0.001`` second) later, the thread starts,
  calls the function and sets the sync event, but it is too late.

Compared to the fake fast-forwarding time, even such fast things as threads
are too slow to start. Unfortunately, ``looptime`` and the event loop can
neither control what is happening outside of the event loop nor predict
how long it will take.

To work around this, ``looptime`` remembers all calls to executors and then
keeps track of the futures they returned. Instead of fast-forwarding the time
by 9 seconds all at once, ``looptime`` fast-forwards the loop's fake time
in small steps and also does a true-time sleep for that step.
So, the fake time and real time move along while waiting for executors.

Luckily for this case, in one or two such steps, the executor's thread will
do its job, and the event will be set, as will the synchronous and asynchronous
futures of the executor. The latter one (the async future) will also
let the ``await`` move on.

The ``idle_step`` (``float`` or ``None``) setting is the duration of a single
time step when fast-forwarding the time if executors are used —
i.e., if some synchronous tasks are running in the thread pools.

Note that the steps are both true-time and fake-time: they spend the same
amount of the observer's true time as they increment the loop's fake time.

A negative side effect: thread spawning can be potentially much faster,
e.g., finish in 0.001 second; but it will be rounded to the round number
of steps with no fractions: e.g., 0.01 or 0.02 seconds in this example.

A trade-off: a smaller step will get results faster but will spend more CPU power on resultless cycles.


Idle I/O activities
===================

Consider this test, which does the external I/O communication:

.. code-block:: python

    import aiohttp
    import pytest


    @pytest.mark.asyncio
    @pytest.mark.looptime
    async def test_me():
        async with aiohttp.ClientSession(timeout=None) as session:
            await session.get('http://some-unresponsive-web-site.com')

How long should it take if there are no implicit timeouts deep in the code?
With no workarounds, the test will hang forever waiting for I/O to happen.
This mostly happens when the only thing left in the event loop is I/O;
all internal scheduled callbacks are gone.

``looptime`` can artificially limit the lifetime of the event loop.
This can be done as a default setting for the whole test suite, for example.

The ``idle_timeout`` (``float`` or ``None``) setting is the true-time limit
of the I/O wait in the absence of scheduled handles/timers/timeouts.
(This I/O includes the dummy I/O used by ``loop.call_soon_threadsafe()``.)
``None`` means there is no timeout waiting for I/O, i.e., it waits forever.
The default is ``1.0`` second.

If nothing happens within this time, the event loop assumes that nothing
will ever happen, so it is a good idea to cease its existence: it injects
:class:`looptime.IdleTimeoutError` (a subclass of :class:`asyncio.TimeoutError`)
into all currently running tasks.

This is similar to how the end-of-time behaves, except that it is measured
in the true-time timeline, while the end-of-time is in the fake-time timeline.
Besides, once I/O happens, the idle timeout is reset, while the end-of-time
can still be reached.

The ``idle_step`` (``float`` or ``None``) setting synchronizes the flow
of the fake-time with the flow of the true-time while waiting for I/O
or synchronous futures, i.e., when nothing happens in the event loop itself.
It sets the single step increment of both timelines.

If the step is not set or set to ``None``, the loop time does not move regardless
of how long the I/O or synchronous futures take in the true time
(with or without the timeout).

If the ``idle_step`` is set, but the ``idle_timeout`` is ``None``,
then the fake time flows naturally in sync with the true time infinitely.

The default is ``None``.


Timeouts vs. the end-of-time
============================

The end of time might look like a global timeout, but it is not the same,
and it is better to use other methods for restricting the execution time:
e.g., `async-timeout <https://github.com/aio-libs/async-timeout>`_
or native ``asyncio.wait_for(…, timeout=…)``.

First, the mentioned approaches can be applied to arbitrary code blocks,
even multiple times independently,
while ``looptime(end=N)`` applies to the lifecycle of the whole event loop,
which is usually the duration of the whole test and monotonically increases.

Second, ``looptime(end=N)`` syncs the loop time with the real time for N seconds,
i.e., it does not instantly fast-forward the loop time when the loop
attempts to make an "infinite sleep" (technically, ``selector.select(None)``).
``async_timeout.timeout()`` and ``asyncio.wait_for()`` set a delayed callback,
so the time fast-forwards to it on the first possible occasion.

Third, once the end-of-time is reached in the event loop, all further attempts
to run async coroutines will fail (except those taking zero loop time).
If the async timeout is reached, further code can proceed normally.

.. code-block:: python

    import asyncio
    import pytest

    @pytest.mark.asyncio
    @pytest.mark.looptime(end=10)
    async def test_the_end_of_time(chronometer, looptime):
        with chronometer:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.Event().wait()
        assert looptime == 10
        assert chronometer >= 10

    @pytest.mark.asyncio
    @pytest.mark.looptime
    async def test_async_timeout(chronometer, looptime):
        with chronometer:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.Event().wait(), timeout=10)
        assert looptime == 10
        assert chronometer < 0.1


Time resolution & floating point precision errors
=================================================

Python (as well as many other languages) has issues with calculating floats:

.. code-block:: python

    >>> 0.2-0.05
    0.15000000000000002
    >>> 0.2-0.19
    0.010000000000000009
    >>> 0.2+0.21
    0.41000000000000003
    >>> 100_000 * 0.000_001
    0.09999999999999999

This can break assertions on time and durations. To work around
the issue, ``looptime`` internally performs all time math in integers.
Time arguments are converted to the internal integer form
and back to the floating-point form when needed.

The ``resolution`` (``float``) setting is the minimum supported time step.
All time steps smaller than that are rounded to the nearest value.

The default is 1 microsecond, i.e., ``0.000001`` (``1e-6``), which is good enough
for typical unit-tests while keeping the integers smaller than 32 bits
(1 second => 20 bits; 32 bits => 4294 seconds ≈1h11m).

Normally, you should not worry about it or configure it.

.. note::

    A side-note: in fact, the reciprocal (1/x) of the resolution is used.
    For example, with a resolution of 0.001, the time
    1.0 (float) becomes 1000 (int),
    0.1 (float) becomes 100 (int),
    0.01 (float) becomes 10 (int),
    0.001 (float) becomes 1 (int);
    everything smaller than 0.001 becomes 0 and probably misbehaves.


Exclusion of fixture setup/teardown
===================================

The time compaction magic is enabled only for the duration of the test,
i.e., the test function — but not the fixtures.
Fixtures run in real (wall-clock) time.

Options (including the forced starting time) are applied at the test function's
starting moment, not when it is setting up the fixtures (even function-scoped).

This is caused by a new concept of multiple co-existing event loops
in pytest-asyncio>=1.0.0:

- It is unclear which options to apply to higher-scoped fixtures
  used by many tests, which themselves use higher-scoped event loops —
  especially in selective partial runs. Technically, it is the first test,
  with the options of the second and subsequent tests simply ignored.
- It is impossible to guess which event loop will be the running loop
  in the test until we reach the test itself, i.e., we do not know this
  when setting up the fixtures, even function-scoped fixtures.
- There is no way to cover the fixture teardown (no hook in pytest),
  only for the fixture setup and post-teardown cleanup.

As such, this functionality (covering of function-scoped fixtures)
was abandoned — since it was never promised, tested, or documented —
plus an assumption that it was never used by anyone (it should not be).
It was rather a side effect of the previous implementation,
which is not available or possible anymore.

If the time magic is needed in fixtures, use the more explicit approach:

.. code-block:: python

    import looptime
    import pytest_async

    @pytest_async.fixture
    def async_fixture_example():
        with looptime.enabled():
            # Execute some async time-based code, but compacted.
            await asyncio.sleep(1)

        # Go to the test(s).
        yield

        with looptime.enabled():
            # Execute some async time-based code, but compacted.
            await asyncio.sleep(1)


pytest-asyncio>=1.0.0
=====================

pytest-asyncio>=1.0.0 introduced several co-existing event loops
of different scopes. Time compaction in these event loops is NOT activated.
Only the running loop of the test function is activated.

Configuring and activating multiple co-existing event loops brings a few
conceptual challenges, which require a good sample case to look into
and some time to think.

Should you need time compaction in your fixtures of higher scopes,
do it explicitly:

.. code-block:: python

    import asyncio
    import pytest

    @pytest.fixture
    async def fixt():
        loop = asyncio.get_running_loop()
        loop.setup_looptime(start=123, end=456)
        with loop.looptime_enabled():
            await do_things()

There is :issue:`11` to add a feature to do this automatically,
but it is not yet done.
