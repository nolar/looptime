# Fast-forward asyncio event loop time (in tests)

[![CI](https://github.com/nolar/looptime/workflows/Thorough%20tests/badge.svg)](https://github.com/nolar/looptime/actions/workflows/thorough.yaml)
[![codecov](https://codecov.io/gh/nolar/looptime/branch/main/graph/badge.svg)](https://codecov.io/gh/nolar/looptime)
[![Coverage Status](https://coveralls.io/repos/github/nolar/looptime/badge.svg?branch=main)](https://coveralls.io/github/nolar/looptime?branch=main)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

## What is this?

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


## What is it not?

It speeds up tests based on the flow of time, in particular various kinds
of timers, timeouts, sleeps, delays, rate limiters
— both in tests and in the system under test.

It does NOT speed up tests that are simply slow with no explicit delays,
such as those involving the local/loopback network communication,
heavy algorithmical compute, slow data moving or processing, etc.
These activities take their fair time and cannot be time-compacted.

It does NOT speed up time-based tests using the synchronous primitives
and the wall-clock time; ``looptime`` compacts only the asyncio time.


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


## Documentation

For more tricks and options, see the [full documentation](https://looptime.readthedocs.io/).
