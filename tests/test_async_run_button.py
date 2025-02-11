import asyncio

import ipywidgets as ipw

import menubox as mb
from menubox import trait_factory as tf
from menubox.widgets import AsyncRunButton

a_kwargs = {}


class PMB(mb.MenuBox):
    task_button_run = tf.Task()
    task_update = tf.Task()
    button = tf.AsyncRunButton(cfunc="_button_async")
    button_sub = tf.AsyncRunButton(cfunc="button", disable_when_sub_button_runs=True)

    async def _button_async(self):
        await asyncio.sleep(0.4)


async def cfunc(**kwargs):
    a_kwargs.update(kwargs)
    await asyncio.sleep(0.1)
    return "OKAY"


async def test_async_run_button():
    parent = PMB()
    assert parent.button.parent is parent, "Auto sets parent"
    task = parent.button.start()
    assert parent.button.task is task
    assert parent.button_sub.disabled is True, "disable_when_sub_button_runs"
    async with asyncio.timeout(1):
        await task
    assert not parent.button.task
    assert parent.button_sub.disabled is False, "disable_when_sub_button_runs"

    b = AsyncRunButton(
        cfunc=cfunc,
        description="my_button",
        kw=lambda: {"a": True},
        parent=parent,
        handle="task_button_run",
    )
    assert parent.task_button_run is None
    task1 = b.start()
    assert b.task is task1
    assert parent.task_button_run is task1
    assert await task1 == "OKAY"
    assert b.task is None
    assert parent.task_button_run is None
    assert a_kwargs["a"] is True

    task2 = b.start(a=False)
    assert task2 is not task1
    task3 = b.start(restart=False, a=False)
    assert task3 is task2
    await task2
    assert a_kwargs["a"] is False

    b.start(a=False)
    await b.cancel_wait()
    assert b.task is None

    await b.start()
    assert b.description == "my_button"

    # Test a nested button
    b2 = AsyncRunButton(
        cfunc=b,
        description="Nested button",
        kw=lambda: {"b": True},
        parent=parent,
        handle="task_update",
    )

    a_kwargs.clear()
    task = b2.start()
    assert parent.task_update is task
    assert task in parent.tasks
    assert b.task
    assert not b.task.done()
    assert b.task in parent.tasks
    assert b.description == "Cancel"
    assert b2.description == "Cancel"
    await task
    assert b2.description == "Nested button"
    assert b.description == "my_button"
    assert a_kwargs["b"] is True
    assert a_kwargs["a"] is True
    assert not b2.task
    assert not parent.tasks
    assert not parent.task_update

    # Test get widgets
    mbox = mb.MenuBox(views={"Main": ipw.HTML("Test")})

    assert mbox.get_widgets([ipw.Box([ipw.Button(disabled=True)])], skip_disabled=True)

    b.discontinue()
    del b
