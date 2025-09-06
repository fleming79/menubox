from typing import Self, cast

import anyio

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
        lambda c: AsyncRunButton(parent=c["owner"], cfunc=lambda p: p.ab_main, description="Sub button"),
        co_=cast(Self, 0),
    )
    data = TF.Dict()

    async def _button_async(self, **kwgs):
        await anyio.sleep(0.4)
        self.data.update(kwgs)
        return kwgs


def has_task(obj: HasParent):
    return bool(getattr(obj, "fut", None))


async def test_async_run_button_description_and_task():
    obj = PMB()
    assert obj.ab_main.description == "Button"
    fut = obj.ab_main.start()
    assert obj.ab_main.fut is fut
    assert fut in obj.futures
    assert obj.ab_main.description == "Cancel"
    await fut
    assert obj.ab_main.description == "Button"
    assert fut not in obj.futures
    assert not obj.ab_main.fut


async def test_async_run_button_kwargs():
    obj = PMB()
    fut = obj.ab_main.start(a=False)
    obj.ab_main.start({"restart": False}, a=False)
    assert obj.ab_main.fut is fut
    await fut
    assert not obj.data.get("a")

    obj.ab_main.start()
    await obj.ab_main.cancel_wait()
    assert not has_task(obj.ab_main)


async def test_async_run_button_nested():
    obj = PMB()
    assert obj.ab_nested.description == "Nested button"
    assert obj.ab_main.description == "Button"
    b_task = obj.ab_main.start(primary=True)
    assert obj.ab_nested_sub.description == "Cancel"
    assert not obj.ab_nested.disabled, "A nested button should be allowed to restart a running task."
    obj.ab_nested.start(description="nested")
    assert b_task.cancelled(), "Starting b2 should cancel b.task before stating a new task"
    assert obj.ab_nested.fut is obj.ab_main.fut
    assert obj.ab_main.fut
    assert obj.ab_main.fut in obj.futures
    assert obj.ab_main.description == "Cancel"
    assert obj.ab_nested.description == "Cancel"
    assert obj.ab_nested.fut
    assert obj.ab_nested.fut in obj.ab_nested.futures
    await obj.ab_nested.wait_tasks()
    # await obj.ab_nested.task
    assert obj.ab_nested.description == "Nested button"
    assert obj.ab_main.description == "Button"
    assert not obj.data.get("primary"), "The task should that sets this should be cancelled"
    assert obj.data.get("description") == "nested", "The kwarg should be passed in the called to button_nest.start"
    assert not obj.ab_nested.fut
    assert not obj.futures
