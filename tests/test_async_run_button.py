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
        co_=cast("Self", 0),
    )
    ab_nested = TF.InstanceHP(
        AsyncRunButton,
        default=lambda c: AsyncRunButton(parent=c["owner"], cfunc=lambda p: p.ab_main, description="Nested button"),
        co_=cast("Self", 0),
    )
    ab_nested_sub = TF.InstanceHP(
        AsyncRunButton,
        lambda c: AsyncRunButton(parent=c["owner"], cfunc=lambda p: p.ab_main, description="Sub button"),
        co_=cast("Self", 0),
    )
    data = TF.Dict()

    async def _button_async(self, **kwgs):
        await anyio.sleep(0.4)
        self.data.update(kwgs)
        return kwgs


def has_pending(obj: HasParent):
    return bool(getattr(obj, "pen", None))


async def test_async_run_button_description_and_pending():
    obj = PMB()
    assert obj.ab_main.description == "Button"
    assert obj.ab_main.icon == "play"
    pen = obj.ab_main.start(False)
    assert obj.ab_main.pen is pen
    assert pen in obj.pending
    assert obj.ab_main.icon == "stop"
    await pen
    assert obj.ab_main.description == "Button"
    assert pen not in obj.pending
    assert not obj.ab_main.pen


async def test_async_run_button_kwargs():
    obj = PMB()
    pending = obj.ab_main.start(False, a=False)
    obj.ab_main.start(False, a=False)
    assert obj.ab_main.pen is pending
    await pending
    assert not obj.data.get("a")

    obj.ab_main.start(False)
    await obj.ab_main.cancel_wait()
    assert not has_pending(obj.ab_main)


async def test_async_run_button_nested():
    obj = PMB()
    assert obj.ab_nested.description == "Nested button"
    assert obj.ab_main.description == "Button"
    b_pen = obj.ab_main.start(False, primary=True)
    assert obj.ab_nested_sub.icon == "stop"
    assert not obj.ab_nested.disabled, "A nested button should be allowed to restart a running pending."
    obj.ab_nested.start(True, description="nested")
    assert b_pen.cancelled(), "Starting b2 should cancel b.pen before stating a new pending"
    assert obj.ab_nested.pen is obj.ab_main.pen
    assert obj.ab_main.pen
    assert obj.ab_main.pen in obj.pending
    assert obj.ab_main.icon == "stop"
    assert obj.ab_nested.icon == "stop"
    assert obj.ab_nested.pen
    assert obj.ab_nested.pen in obj.ab_nested.pending
    await obj.ab_nested.wait_pending()

    assert obj.ab_nested.description == "Nested button"
    assert obj.ab_main.icon == "play"
    assert not obj.data.get("primary"), "The pending should that sets this should be cancelled"
    assert obj.data.get("description") == "nested", "The kwarg should be passed in the called to button_nest.start"
    assert not obj.ab_nested.pen
    assert not obj.pending
