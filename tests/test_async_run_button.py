import asyncio
from typing import Self, cast

import menubox as mb
from menubox.async_run_button import AsyncRunButton
from menubox.hasparent import HasParent
from menubox.trait_factory import TF


class PMB(mb.Menubox):
    ab_main = TF.InstanceHP(
        AsyncRunButton,
        lambda c: AsyncRunButton(parent=c["owner"], cfunc=lambda p: p._button_async, description="Button"),
        co_=cast(Self, 0),
    )
    ab_nested = TF.InstanceHP(
        AsyncRunButton,
        default=lambda c: AsyncRunButton(parent=c["owner"], cfunc=lambda p: p.ab_main, description="Nested button"),
        co_=cast(Self, 0),
    )
    ab_nested_sub = TF.InstanceHP(
        AsyncRunButton,
        lambda c: AsyncRunButton(
            parent=c["owner"], cfunc=lambda p: p.ab_main, description="Sub button", link_button=True
        ),
        co_=cast(Self, 0),
    )
    data = TF.Dict()

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
    assert task in obj.tasks
    assert obj.ab_main.description == "Cancel"
    await task
    assert obj.ab_main.description == "Button"
    assert task not in obj.tasks
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
    assert obj.ab_main.task
    assert obj.ab_main.task in obj.tasks
    assert obj.ab_main.description == "Cancel"
    assert obj.ab_nested.description == "Cancel"
    assert obj.ab_nested.task
    assert obj.ab_nested.task in obj.ab_nested.tasks
    await obj.ab_nested.wait_tasks()
    # await obj.ab_nested.task
    assert obj.ab_nested.description == "Nested button"
    assert obj.ab_main.description == "Button"
    assert not obj.data.get("primary"), "The task should that sets this should be cancelled"
    assert obj.data.get("nested"), "The kwarg should be passed in the called to button_nest.start"
    assert not obj.ab_nested.task
    assert not obj.tasks


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
