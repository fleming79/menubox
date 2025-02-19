import asyncio

import traitlets

import menubox as mb
from menubox import trait_factory as tf
from menubox.hasparent import HasParent


class PMB(mb.MenuBox):
    ab_main = tf.AsyncRunButton(cfunc="_button_async", description="Button")
    ab_nested = tf.AsyncRunButton(cfunc="ab_main", description="Nested button")
    ab_nested_sub = tf.AsyncRunButton(cfunc="ab_main", description="Sub button", link_button=True)
    data = traitlets.Dict()

    async def _button_async(self, **kwgs):
        await asyncio.sleep(0.4)
        self.data.update(kwgs)
        return kwgs


def has_task(obj: HasParent):
    return bool(getattr(obj, "task", None))


async def test_async_run_button_description_and_task():
    obj = PMB()
    assert obj.ab_main.description == "Button"
    task = obj.ab_main.start()
    assert obj.ab_main.task is task
    assert task in obj.mb_tasks
    assert obj.ab_main.description == "Cancel"
    await task
    assert obj.ab_main.description == "Button"
    assert task not in obj.mb_tasks
    assert not obj.ab_main.task


async def test_async_run_button_kwargs():
    obj = PMB()
    task = obj.ab_main.start(a=False)
    obj.ab_main.start(restart=False, a=False)
    assert obj.ab_main.task is task
    await task
    assert not obj.data.get("a")

    obj.ab_main.start()
    await obj.ab_main.cancel_wait()
    assert not has_task(obj.ab_main)


async def test_async_run_button_nested():
    obj = PMB()
    assert obj.ab_nested.description == "Nested button"
    assert obj.ab_main.description == "Button"
    b_task = obj.ab_main.start(primary=True)
    assert obj.ab_nested_sub.disabled, "A sub button should disable when the main button has a task"
    assert not obj.ab_nested.disabled, "A nested button should be allowed to restart a running task."
    obj.ab_nested.start(nested=True)
    assert b_task.cancelling(), "Starting b2 should cancel b.task before stating a new task"
    assert obj.ab_nested.task is obj.ab_main.task
    assert not obj.ab_main.task.done()
    assert obj.ab_main.task in obj.mb_tasks
    assert obj.ab_main.description == "Cancel"
    assert obj.ab_nested.description == "Cancel"
    await obj.ab_nested.task
    assert obj.ab_nested.description == "Nested button"
    assert obj.ab_main.description == "Button"
    assert not obj.data.get("primary"), "The task should that sets this should be cancelled"
    assert obj.data.get("nested"), "The kwarg should be passed in the called to button_nest.start"
    assert not obj.ab_nested.task
    assert not obj.mb_tasks


async def test_async_run_button_link_button():
    obj = PMB()
    assert obj.ab_main.parent is obj, "Auto sets parent"
    task = obj.ab_main.start()
    assert obj.ab_main.task is task
    assert obj.ab_nested_sub.disabled is True, "link_button"
    await task
    assert not obj.ab_main.task
    assert obj.ab_nested_sub.disabled is False, "link_button"


async def test_async_run_no_restart():
    # Passing restart=False should always return None
    obj = PMB()
    assert await obj.ab_main.start(restart=False, ab_main=True) is None
    assert "ab_main" in obj.data
    assert await obj.ab_nested.start(restart=False, nested=True) is None
    assert "nested" in obj.data
    assert await obj.ab_nested_sub.start(restart=False, sub=True) is None
    assert "sub" in obj.data
