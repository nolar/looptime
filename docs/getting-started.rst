===============
Getting Started
===============

Installation
============

First, install the necessary packages. We assume that the async tests are
supported. For example, use `pytest-asyncio <https://github.com/pytest-dev/pytest-asyncio>`_:

.. code-block:: bash

    pip install pytest-asyncio
    pip install looptime


Activation from CLI
===================

Nothing is needed to make async tests run with the fake time, it just works:

.. code-block:: python

    import asyncio
    import pytest


    @pytest.mark.asyncio
    async def test_me():
        await asyncio.sleep(100)
        assert asyncio.get_running_loop().time() == 100

Run it with the ``--looptime`` flag:

.. code-block:: bash

    pytest --looptime

The test will be executed in approximately **0.01 seconds**,
while the event loop believes it is 100 seconds old.


Activation by marks
===================

If the command line or ini-file options for all tests is not desirable,
individual tests can be marked for fast time forwarding explicitly:

.. code-block:: python

    import asyncio
    import pytest


    @pytest.mark.asyncio
    @pytest.mark.looptime
    async def test_me():
        await asyncio.sleep(100)
        assert asyncio.get_running_loop().time() == 100

Then just run regular pytest:

.. code-block:: bash

    pytest

Under the hood, the library solves some nuanced situations with time in tests.
See :doc:`nuances` for more complicated (and nuanced) examples.
