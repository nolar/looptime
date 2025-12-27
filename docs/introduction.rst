============
Introduction
============

What?
=====

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

The library was originally developed for `Kopf <https://github.com/nolar/kopf>`_,
a framework for `Kubernetes Operators in Python <https://github.com/nolar/kopf>`_,
which actively uses asyncio tests in pytest (≈7000 unit-tests in ≈2 minutes).
You can see how this library changes and simplifies the tests in
`Kopf's PR #881 <https://github.com/nolar/kopf/pull/881>`_.


Why?
====

Without ``looptime``, the event loops use ``time.monotonic()`` for the time,
which also captures the code overhead and the network latencies, adding little
random fluctuations to the time measurements (approx. 0.01-0.001 seconds).

Without ``looptime``, the event loops spend the real wall-clock time
when there is no i/o happening but some callbacks are scheduled for later.
In controlled environments like unit tests and fixtures, this time is wasted.

Also, because I can! (It was a little over-engineering exercise for fun.)


Problem
=======

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


Solution
========

Similar to the mentioned approaches, to address this issue, ``looptime``
takes care of mocking the event loop and removes this hassle from the tests.

However, unlike the tests, ``looptime`` does not mock the typically used
low-level coroutines (e.g. sleep), primitives (e.g. events/conditions),
or library calls (e.g. requests getting/posting, sockets reading/writing, etc).

``looptime`` goes deeper and mocks the very foundation of it all — the time itself.
Then, it controllably moves the time forward in sharp steps when the event loop
requests the actual true-time sleep from the underlying selectors (i/o sockets).
