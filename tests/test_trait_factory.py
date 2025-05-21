import asyncio
from typing import Self, cast

import pytest
from traitlets import TraitError

from menubox import HasParent
from menubox.trait_factory import TF


class TestTraitFactory:
    async def test_base_types(self):
        class BaseTest(HasParent):
            str = TF.Str()
            int = TF.Int(0)
            float = TF.Float()
            dict = TF.Dict()
            set = TF.Set()
            tuple = TF.Tuple()

        base = BaseTest()
        assert isinstance(base.str, str)
        assert isinstance(base.int, int)
        assert isinstance(base.float, float)
        assert isinstance(base.dict, dict)
        assert isinstance(base.set, set)
        assert isinstance(base.tuple, tuple)

    async def test_parent(self):
        p = HasParent()
        assert p.parent is None
        obj = HasParent(parent=p)
        assert obj.parent is p
        with pytest.raises(TraitError, match="Unable to set parent of"):
            p.parent = obj

    async def test_button_restart_mode(self):
        class BaseTestButton(HasParent):
            button = TF.Button(cast(Self, 0), mode=TF.ButtonMode.restart)
            clicked = TF.Dict()

            async def button_clicked(self, b):
                self.clicked[b] = asyncio.current_task()
                await asyncio.Event().wait()

        obj = BaseTestButton()
        obj.button.click()
        await asyncio.sleep(0)
        t1 = obj.clicked.get(obj.button)
        assert isinstance(t1, asyncio.Task)
        obj.button.click()
        assert t1.cancelling() == 1
        await asyncio.wait([t1])
        await asyncio.sleep(0)
        t2 = obj.clicked.get(obj.button)
        assert isinstance(t2, asyncio.Task)
        assert t2 is not t1
        t2.cancel()

    async def test_button_cancel_mode(self):
        class BaseTestButton(HasParent):
            button = TF.Button(
                cast(
                    Self,
                    0,
                ),
                mode=TF.ButtonMode.cancel,
                description="My button",
            )
            clicked = TF.Dict()

            async def button_clicked(self, b):
                self.clicked[b] = asyncio.current_task()
                await asyncio.Event().wait()

        obj = BaseTestButton()
        obj.button.click()
        await asyncio.sleep(0)
        assert obj.button.description == "Cancel"
        t1 = obj.clicked.get(obj.button)
        assert isinstance(t1, asyncio.Task)
        obj.button.click()
        assert t1.cancelling() == 1
        await asyncio.wait([t1])
        await asyncio.sleep(0)
        t2 = obj.clicked.get(obj.button)
        assert isinstance(t2, asyncio.Task)
        assert t2 is t1
        assert obj.button.description == "My button"

    async def test_button_disable_mode(self):
        class BaseTestButton(HasParent):
            button = TF.Button(cast(Self, 0), mode=TF.ButtonMode.disable)
            clicked = TF.Dict()

            async def button_clicked(self, b):
                self.clicked[b] = asyncio.current_task()
                await asyncio.Event().wait()

        obj = BaseTestButton()
        obj.button.click()
        await asyncio.sleep(0)
        t1 = obj.clicked.get(obj.button)
        assert isinstance(t1, asyncio.Task)
        assert obj.button.disabled
        t1.cancel()
        await asyncio.wait([t1])
        assert not obj.button.disabled
