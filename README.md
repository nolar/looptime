# Fast-forward asyncio event loop time (in tests)

[![CI](https://github.com/nolar/looptime/workflows/Thorough%20tests/badge.svg)](https://github.com/nolar/looptime/actions/workflows/thorough.yaml)
[![codecov](https://codecov.io/gh/nolar/looptime/branch/main/graph/badge.svg)](https://codecov.io/gh/nolar/looptime)
[![Coverage Status](https://coveralls.io/repos/github/nolar/looptime/badge.svg?branch=main)](https://coveralls.io/github/nolar/looptime?branch=main)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

## What?

Fake the flow of time in asyncio event loops.
The effects of time removal can be seen from both sides:

* From the **event loop's (i.e. your tests') point of view,**
  all external activities, such as synchronous executor calls (thread pools)
  and i/o with sockets, servers, files, happen in zero amount of the loop time —
  even if it takes some real time.
  This hides the code overhead and network latencies from the time measurements,
  making the loop time sharply and predictably advancing in configured steps.

* From the **observer's (i.e. your personal) point of view,**
  all activities of the event loop, such as sleeps, events/conditions waits,
  timeouts, "later" callbacks, happen in near-zero amount of the real time
  (due to the usual code execution overhead).
  This speeds up the execution of tests without breaking the tests' time-based
  design, even if they are designed to run in seconds or minutes.

For the latter case, there are a few exceptions when the event loop's activities
are synced with the true-time external activities, such as thread pools or i/o,
so that they spend the real time above the usual code overhead (if configured).

The library was originally developed for [Kopf](https://github.com/nolar/kopf),
a framework for [Kubernetes Operators in Python](https://github.com/nolar/kopf),
which actively uses asyncio tests in pytest (≈7000 unit-tests in ≈2 minutes).
You can see how this library changes and simplifies the tests in
[Kopf's PR #881](https://github.com/nolar/kopf/pull/881).


## Why?

Without `looptime`, the event loops use `time.monotonic()` for the time,
which also captures the code overhead and the network latencies, adding little
random fluctuations to the time measurements (approx. 0.01-0.001 seconds).

Without `looptime`, the event loops spend the real wall-clock time
when there is no i/o happening but some callbacks are scheduled for later.
In controlled environments like unit tests and fixtures, this time is wasted.

Also, because I can! (It was a little over-engineering exercise for fun.)


## Problem

It is difficult to test complex asynchronous coroutines with the established
unit-testing practices since there are typically two execution flows happening
at the same time:

* One is for the coroutine-under-test which moves between states
  in the background.
* Another one is for the test itself, which controls the flow
  of that coroutine-under-test: it schedules events, injects data, etc.

In textbook cases with simple coroutines that are more like regular functions,
it is possible to design a test so that it runs straight to the end in one hop
— with all the preconditions set and data prepared in advance in the test setup.

However, in the real-world cases, the tests often must verify that
the coroutine stops at some point, waits for a condition for some limited time,
and then passes or fails.

The problem is often "solved" by mocking the low-level coroutines of sleep/wait
that we expect the coroutine-under-test to call. But this violates the main
principle of good unit-tests: **test the promise, not the implementation.**
Mocking and checking the low-level coroutines is based on the assumptions
of how the coroutine is implemented internally, which can change over time.
Good tests do not change on refactoring if the protocol remains the same.

Another (straightforward) approach is to not mock the low-level routines, but
to spend the real-world time, just in short bursts as hard-coded in the test.
Not only it makes the whole test-suite slower, it also brings the execution
time close to the values where the code overhead or measurement errors affect
the timing, which makes it difficult to assert on the coroutine's pure time.


## Solution

Similar to the mentioned approaches, to address this issue, `looptime`
takes care of mocking the event loop and removes this hassle from the tests.

However, unlike the tests, `looptime` does not mock the typically used
low-level coroutines (e.g. sleep), primitives (e.g. events/conditions),
or library calls (e.g. requests getting/posting, sockets reading/writing, etc).

`looptime` goes deeper and mocks the very foundation of it all — the time itself.
Then, it controllably moves the time forward in sharp steps when the event loop
requests the actual true-time sleep from the underlying selectors (i/o sockets).


## Examples

Here, we assume that the async tests are supported. For example,
use [`pytest-asyncio`](https://github.com/pytest-dev/pytest-asyncio):

```bash
pip install pytest-asyncio
pip install looptime
```

Nothing is needed to make async tests run with the fake time, it just works:

```python
import asyncio
import pytest


@pytest.mark.asyncio
async def test_me():
    await asyncio.sleep(100)
    assert asyncio.get_running_loop().time() == 100
```

```bash
pytest --looptime
```

The test will be executed in approximately **0.01 seconds**,
while the event loop believes it is 100 seconds old.

If the command line or ini-file options for all tests is not desirable,
individual tests can be marked for fast time forwarding explicitly:

```python
import asyncio
import pytest


@pytest.mark.asyncio
@pytest.mark.looptime
async def test_me():
    await asyncio.sleep(100)
    assert asyncio.get_running_loop().time() == 100
```

```bash
pytest
```

Under the hood, the library solves some nuanced situations with time in tests.
See "Nuances" below for more complicated (and nuanced) examples.


## Markers

`@pytest.mark.looptime` configures the test's options if and when it is
executed with the timeline replaced to fast-forwarding time.
In normal mode with no configs/CLI options specified,
it marks the test to be executed with the time replaced.

`@pytest.mark.looptime(False)` (with the positional argument)
excludes the test from the time fast-forwarding under any circumstances.
The test will be executed with the loop time aligned with the real-world time.
Use it only for the tests that are designed to be true-time-based.

Note that markers can be applied not only to individual tests,
but also to whole test suites (classes, modules, packages):

```python
import asyncio
import pytest

pytestmark = [
  pytest.mark.asyncio,
  pytest.mark.looptime(end=60),
]


async def test_me():
    await asyncio.sleep(100)
```

The markers can also be artificially injected by plugins/hooks if needed:

```python
import inspect
import pytest

@pytest.hookimpl(hookwrapper=True)
def pytest_pycollect_makeitem(collector, name, obj):
    if collector.funcnamefilter(name) and inspect.iscoroutinefunction(obj):
        pytest.mark.asyncio(obj)
        pytest.mark.looptime(end=60)(obj)
    yield
```

All in all, the `looptime` plugin uses the most specific (the "closest") value
for each setting separately (i.e. not the closest marker as a whole).


## Options

`--looptime` enables time fast-forwarding for all tests that are not explicitly
marked as using the fake loop time —including those not marked at all—
as if all tests were implicitly marked.

`--no-looptime` runs all tests —both marked and unmarked— with the real time.
This flag effectively disables the plugin.


## Settings

The marker accepts several settings for the test. The closest to the test
function applies. This lets you define the test-suite defaults
and override them on the directory, module, class, function, or test level:

```python
import asyncio
import pytest

pytestmark = pytest.mark.looptime(end=10, idle_timeout=1)

@pytest.mark.asyncio
@pytest.mark.looptime(end=101)
async def test_me():
    await asyncio.sleep(100)
    assert asyncio.get_running_loop().time() == 100
```


### The time zero

`start` (`float` or `None`, or a no-argument callable that returns the same)
is the initial time of the event loop.

If it is a callable, it is invoked once per event loop to get the value:
e.g. `start=time.monotonic` to align with the true time,
or `start=lambda: random.random() * 100` to add some unpredictability.

`None` is treated the same as `0.0`.

The default is `0.0`. For reusable event loops, the default is to keep
the time untouched, which means `0.0` or the explicit value for the first test,
but then an ever-increasing value for the 2nd, 3rd, and further tests.

Note: pytest-asyncio 1.0.0+ introduced event loops with higher scopes,
e.g. class-, module-, packages-, session-scoped event loops used in tests.
Such event loops are reused, so their time continues growing through many tests.
However, if the test is explicitly configured with the start time,
that time is enforced to the event loop when the test function starts —
to satisfy the clearly declared intentions — even if the time moves backwards,
which goes against the nature of the time itself (monotonically growing).
This might lead to surprises in time measurements outside of the test,
e.g. in fixtures: the code durations can become negative, or the events can
happen (falsely) before they are scheduled (loop-clock-wise). Be careful.


### The end of time

`end` (`float` or `None`, or a no-argument callable that returns the same)
is the final time in the event loop (the internal fake time).
If it is reached, all tasks get terminated and the test is supposed to fail.
The injected exception is `LoopTimeoutError`,
a subclass of `asyncio.TimeoutError`.

All test-/fixture-finalizing routines will have their fair chance to execute
as long as they do not move the loop time forward, i.e. they take zero time:
e.g. with `asyncio.sleep(0)`, simple `await` statements, etc.

If set to `None`, there is no end of time, and the event loop runs
as long as needed. Note: `0` means ending the time immediately on start.
Be careful with the explicit ending time in higher-scoped event loops
of pytest-asyncio>=1.0.0, since they time increases through many tests.

If it is a callable, it is called once per event loop to get the value:
e.g. `end=lambda: time.monotonic() + 10`.

The end of time is not the same as timeouts — see the nuances below
on differences with `async-timeout`.


## Nuances

### Preliminary execution

Consider this test:

```python
import asyncio
import async_timeout
import pytest


@pytest.mark.asyncio
@pytest.mark.looptime
async def test_me():
    async with async_timeout.timeout(9):
        await asyncio.sleep(1)
```

Normally, it should not fail. However, with fake time (without workarounds)
the following scenario is possible:

* `async_timeout` library sets its delayed timer at 9 seconds since now.
* the event loop notices that there is only one timer at T0+9s.
* the event loop fast-forwards time to be `9`.
* since there are no other handles/timers, that timer is executed.
* `async_timeout` fails the test with `asyncio.TimeoutError`
* The `sleep()` never gets any chance to be scheduled or executed.

To solve this, `looptime` performs several dummy zero-time no-op cycles
before actually moving the time forward. This gives other coroutines,
tasks, and handles their fair chance to be entered, spawned, scheduled.
This is why the example works as intended.

The `noop_cycles` (`int`) setting is how many cycles the event loop makes.
The default is `42`. Why 42? Well, …


### Slow executors

Consider this test:

```python
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
```

With the true time, this test will finish in a fraction of a second.
However, with the fake time (with no workarounds), the following happens:

* A new synchronous event is created, it is unset by default.
* A synchronous task is submitted to a thread pool executor.
* The thread pool starts spawning a new thread and passing the task there.
* An asynchronous awaitable (future) is returned, which is chained
  with its synchronous counterpart.
* `looptime` performs its no-op cycles, letting all coroutines to start,
  but it does this in near-zero true-time.
* The event loop forwards its time to 9 seconds and raises a timeout error.
* The test suppresses the timeout, checks the assertion, and fails:
  the sync event is still unset.
* A fraction of a second (e.g. `0.001` second) later, the thread starts,
  calls the function and sets the sync event, but it is too late.

Compared to the fake fast-forwarding time, even such fast things as threads
are too slow to start. Unfortunately, `looptime` and the event loop can
neither control what is happening outside of the event loop nor predict
how long it will take.

To work around this, `looptime` remembers all calls to executors and then
keeps track of the futures they returned. Instead of fast-forwarding the time
by 9 seconds all at once, `looptime` fast-forwards the loop's fake time
in small steps and also does the true-time sleep for that step.
So, the fake time and real time move along while waiting for executors.

Luckily for this case, in 1 or 2 such steps, the executor's thread will
do its job, the event will be set, so as the synchronous & asynchronous
futures of the executor. The latter one (the async future) will also
let the `await` move on.

The `idle_step` (`float` or `None`) setting is the duration of a single
time step when fast-forwarding the time if there are executors used —
i.e. if some synchronous tasks are running in the thread pools.

Note that the steps are both true-time and fake-time: they spend the same
amount of the observer's true time as they increment the loop's fake time.

A negative side effect: the thread spawning can be potentially much faster,
e.g. finish in in 0.001 second; but it will be rounded to be the round number
of steps with no fractions: e.g. 0.01 or 0.02 seconds in this example.

A trade-off: the smaller step will get the results faster,
but will spend more CPU power on resultless cycles.


### I/O idle

Consider this test:

```python
import aiohttp
import pytest


@pytest.mark.asyncio
@pytest.mark.looptime
async def test_me():
    async with aiohttp.ClientSession(timeout=None) as session:
        await session.get('http://some-unresponsive-web-site.com')
```

How long should it take if there are no implicit timeouts deep in the code?
With no workarounds, the test will hang forever waiting for the i/o to happen.
This mostly happens when the only thing left in the event loop is the i/o,
all internal scheduled callbacks are gone.

`looptime` can artificially limit the lifetime of the event loop.
This can be done as a default setting for the whole test suite, for example.

The `idle_timeout` (`float` or `None`) setting is the true-time limit
of the i/o wait in the absence of scheduled handles/timers/timeouts.
(This i/o includes the dummy i/o used by `loop.call_soon_threadsafe()`.)
`None` means there is no timeout waiting for the i/o, i.e. it waits forever.
The default is `1.0` seconds.

If nothing happens within this time, the event loop assumes that nothing
will happen ever, so it is a good idea to cease its existence: it injects
`IdleTimeoutError` (a subclass of `asyncio.TimeoutError`) into all tasks.

This is similar to how the end-of-time behaves, except that it is measured
in the true-time timeline, while the end-of-time is the fake-time timeline.
Besides, once an i/o happens, the idle timeout is reset, while the end-of-time
still can be reached.

The `idle_step` (`float` or `None`) setting synchronises the flow
of the fake-time with the flow of the true-time while waiting for the i/o
or synchronous futures, i.e. when nothing happens in the event loop itself.
It sets the single step increment of both timelines.

If the step is not set or set to `None`, the loop time does not move regardless
of how long the i/o or synchronous futures take in the true time
(with or without the timeout).

If the `idle_step` is set, but the `idle_timeout` is `None`,
then the fake time flows naturally in sync with the true time infinitely.

The default is `None`.


### Timeouts vs. the end-of-time

The end of time might look like a global timeout, but it is not the same,
and it is better to use other methods for restricting the execution time:
e.g. [`async-timeout`](https://github.com/aio-libs/async-timeout)
or native `asyncio.wait_for(…, timeout=…)`.

First, the mentioned approaches can be applied to arbitrary code blocks,
even multiple times independently,
while `looptime(end=N)` applies to the lifecycle of the whole event loop,
which is usually the duration of the whole test and monotonically increases.

Second, `looptime(end=N)` syncs the loop time with the real time for N seconds,
i.e. it does not instantly fast-forward the loop time when the loops
attempts to make an "infinite sleep" (technically, `selector.select(None)`).
`async_timeout.timeout()` and `asyncio.wait_for()` set a delayed callback,
so the time fast-forwards to it on the first possible occasion.

Third, once the end-of-time is reached in the event loop, all further attempts
to run async coroutines will fail (except those taking zero loop time).
If the async timeout is reached, further code can proceed normally.

```python
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
```


### Time resolution

Python (so as many other languages) has issues with calculating the floats:

```
>>> 0.2-0.05
0.15000000000000002
>>> 0.2-0.19
0.010000000000000009
>>> 0.2+0.21
0.41000000000000003
>>> 100_000 * 0.000_001
0.09999999999999999
```

This can break the assertions on the time and durations. To work around
the issue, `looptime` internally performs all the time math in integers.
The time arguments are converted to the internal integer form
and back to the floating-point form when needed.

The `resolution` (`float`) setting is the minimum supported time step.
All time steps smaller than that are rounded to the nearest value.

The default is 1 microsecond, i.e. `0.000001` (`1e-6`), which is good enough
for typical unit-tests while keeps the integers smaller than 32 bits
(1 second => 20 bits; 32 bits => 4294 seconds ≈1h11m).

Normally, you should not worry about it or configure it.

_A side-note: in fact, the reciprocal (1/x) of the resolution is used.
For example, with the resolution `0.001`, the time
`1.0` (float) becomes `1000` (int),
`0.1` (float) becomes `100` (int),
`0.01` (float) becomes `10` (int),
`0.001` (float) becomes `1` (int);
everything smaller than `0.001` becomes `0` and probably misbehaves._


### Time magic coverage

The time compaction magic is enabled only for the duration of the test,
i.e. the test function — but not the fixtures.
The fixtures run in the real (wall-clock) time.

The options (including the force starting time) are applied at the test function
starting moment, not when it is setting up the fixtures (even function-scoped).

This is caused by a new concept of multiple co-existing event loops
in pytest-asyncio>=1.0.0:

- It is unclear which options to apply to higher-scoped fixtures
  used by many tests, which themselves use higher-scoped event loops —
  especially in selective partial runs. Technically, it is the 1st test,
  with the options of 2nd and further tests simply ignored.
- It is impossible to guess which event loop will be the running loop
  in the test until we reach the test itself, i.e. we do not know this
  when setting up the fixtures, even function-scoped fixtures.
- There is no way to cover the fixture teardown (no hook in pytest),
  only for the fixture setup and post-teardown cleanup.

As such, this functionality (covering of function-scoped fixtures)
was abandoned — since it was never promised, tested, or documented —
plus an assumption that it was never used by anyone (it should not be).
It was rather a side effect of the previous implemention,
which is not available or possible anymore.


### pytest-asyncio>=1.0.0

As it is said above, pytest-asyncio>=1.0.0 introduced several co-existing
event loops of different scopes. The time compaction in these event loops
is NOT activated. Only the running loop of the test function is activated.

Configuring and activating multiple co-existing event loops brings a few
conceptual challenges, which require a good sample case to look into,
and some time to think.

Would you need time compaction in your fixtures of higher scopes,
do it explicitly:

```python
import asyncio
import pytest

@pytest.fixture
async def fixt():
    loop = asyncio.get_running_loop()
    loop.setup_looptime(start=123, end=456)
    with loop.looptime_enabled():
        await do_things()
```

There is #11 to add a feature to do this automatically, but it is not yet done.


## Extras

### Chronometers

For convenience, the library also provides a class and a fixture
to measure the duration of arbitrary code blocks in real-world time:

* `looptime.Chronometer` (a context manager class).
* `chronometer` (a pytest fixture).

It can be used as a sync or async context manager:

```python
import asyncio
import pytest

@pytest.mark.asyncio
@pytest.mark.looptime
async def test_me(chronometer):
    with chronometer:
        await asyncio.sleep(1)
        await asyncio.sleep(1)
    assert chronometer.seconds < 0.01  # random code overhead
```

Usually, the loop-time duration is not needed or can be retrieved via
`asyncio.get_running_loop().time()`. If needed, it can be measured using
the provided context manager class with the event loop's clock:

```python
import asyncio
import looptime
import pytest

@pytest.mark.asyncio
@pytest.mark.looptime(start=100)
async def test_me(chronometer, event_loop):
    with chronometer, looptime.Chronometer(event_loop.time) as loopometer:
        await asyncio.sleep(1)
        await asyncio.sleep(1)
    assert chronometer.seconds < 0.01  # random code overhead
    assert loopometer.seconds == 2  # precise timing, no code overhead
    assert event_loop.time() == 102
```


### Loop time assertions

The `looptime` **fixture** is syntax sugar for easy loop time assertions::

```python
import asyncio
import pytest

@pytest.mark.asyncio
@pytest.mark.looptime(start=100)
async def test_me(looptime):
    await asyncio.sleep(1.23)
    assert looptime == 101.23
```

Technically, it is a proxy object to `asyncio.get_running_loop().time()`.
The proxy object supports the direct comparison with numbers (integers/floats),
so as some basic arithmetics (adding, subtracting, multiplication, etc).
However, it adjusts to the time precision of 1 nanosecond (1e-9): every digit
beyond that precision is ignored — so you can be not afraid of
`123.456/1.2` suddenly becoming `102.88000000000001` and not equal to `102.88`
(as long as the time proxy object is used and not converted to a native float).

The proxy object can be used to create a new proxy that is bound to a specific
event loop (it works for loops both with fake- and real-world time)::

```python
import asyncio
from looptime import patch_event_loop

def test_me(looptime):
    new_loop = patch_event_loop(asyncio.new_event_loop(), start=100)
    new_loop.run_until_complete(asyncio.sleep(1.23))
    assert looptime @ new_loop == 101.23
```

Mind that it is not the same as `Chronographer` for the whole test.
The time proxy reflects the time of the loop, not the duration of the test:
the loop time can start at a non-zero point; even if it starts at zero,
the loop time also includes the time of all fixtures setups.


### Custom event loops

Do you use a custom event loop? No problem! Create a test-specific descendant
with the provided mixin — and it will work the same as the default event loop.

For `pytest-asyncio<1.0.0`:

```python
import looptime
import pytest
from wherever import CustomEventLoop


class LooptimeCustomEventLoop(looptime.LoopTimeEventLoop, CustomEventLoop):
  pass


@pytest.fixture
def event_loop():
    return LooptimeCustomEventLoop()
```

For `pytest-asyncio>=1.0.0`:

```python
import asyncio
import looptime
import pytest
from wherever import CustomEventLoop


class LooptimeCustomEventLoop(looptime.LoopTimeEventLoop, CustomEventLoop):
    pass


class LooptimeCustomEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    def new_event_loop(self):
        return LooptimeCustomEventLoop()


@pytest.fixture(scope='session')
def event_loop_policy():
    return LooptimeCustomEventLoopPolicy()
```

Only selector-based event loops are supported: the event loop must rely on
`self._selector.select(timeout)` to sleep for `timeout` true-time seconds.
Everything that inherits from `asyncio.BaseEventLoop` should work.

You can also patch almost any event loop class or event loop object
the same way as `looptime` does that (via some dirty hackery):

For `pytest-asyncio<1.0.0`:

```python
import asyncio
import looptime
import pytest


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    return looptime.patch_event_loop(loop)
```

For `pytest-asyncio>=1.0.0`:

```python
import asyncio
import looptime
import pytest


class LooptimeEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    def new_event_loop(self):
        loop = super().new_event_loop()
        return looptime.patch_event_loop(loop)


@pytest.fixture(scope='session')
def event_loop_policy():
    return LooptimeEventLoopPolicy()
```

`looptime.make_event_loop_class(cls)` constructs a new class that inherits
from the referenced class and the specialised event loop class mentioned above.
The resulting classes are cached, so it can be safely called multiple times.

`looptime.patch_event_loop()` replaces the event loop's class with the newly
constructed one. For those who care, it is an equivalent of the following hack
(some restrictions apply to the derived class):

```python
loop.__class__ = looptime.make_event_loop_class(loop.__class__)
```
