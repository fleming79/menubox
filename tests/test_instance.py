from __future__ import annotations

import asyncio
import gc
import weakref
from typing import Self, cast

import ipywidgets as ipw
import pytest
from traitlets import TraitError

import menubox as mb
from menubox.hashome import HasHome
from menubox.hasparent import HasParent
from menubox.instance import InstanceHP, instanceHP_wrapper
from menubox.trait_factory import TF

Dropdown = instanceHP_wrapper(ipw.Dropdown, defaults={"options": [1, 2, 3]})


class HPI(mb.Menubox):
    a = InstanceHP("tests.test_instance.HPI", default=lambda c: HPI(name="a", **c["kwgs"])).configure(TF.IHPMode.XL_N)
    b = InstanceHP("tests.test_instance.HPI", default=lambda c: HPI(name="b", **c["kwgs"])).configure(TF.IHPMode.X___)
    my_button = TF.Button(description="A button")
    box = TF.HBox().hooks(set_children={"dottednames": ("my_button",), "mode": "monitor"})
    clicked = 0

    async def button_clicked(self, b: ipw.Button):
        match b:
            case self.my_button:
                self.clicked = self.clicked + 1
            case _:
                await super().button_clicked(b)


class HPI2(HasHome, HPI, mb.MenuboxVT):
    c = InstanceHP(HPI, default=lambda _: HPI(name="C has value")).hooks(set_parent=False)
    e = Dropdown(description="From a factory").configure(TF.IHPMode.XLRN)
    select_repository = TF.SelectRepository(cast(Self, 0))
    button = TF.AsyncRunButton(cast(Self, 0), cfunc=lambda p: p._button_async)
    widgetlist = mb.StrTuple("select_repository", "not a widget")

    async def _button_async(self):
        return True


class HPI3(mb.Menubox):
    box = TF.Box().configure(TF.IHPMode.XLRN)
    menubox = TF.Menubox(views={"main": None}).configure(TF.IHPMode.XLRN)
    hpi2 = TF.InstanceHP(HPI2, default=lambda _: HPI2(home="test")).configure(TF.IHPMode.XLRN)


class HPI4(HasHome):
    hpi = TF.InstanceHP(HPI).configure(TF.IHPMode.XLRN)
    hpi.hooks(value_changed=lambda c: c["parent"].set_trait("value_changed", c))
    value_changed = TF.Dict()


class TestInstance:
    async def test_instance(self, home: mb.Home):
        hp1 = HPI(name="hp1")
        assert hp1.my_button
        assert hp1.a
        assert hp1.a.name
        # Spawn from Class name
        assert isinstance(hp1.a, HPI)
        with pytest.raises(TraitError):
            assert not hp1.b, "`None` is not allowed for"
        assert hp1.a.name == "a"
        assert hp1.a.parent is hp1

        hp2 = HPI2(a=None, home=home)
        hp2.enable_ihp("b", override={"b": hp1, "a": None})
        assert not hp2.a, "Disabled during init"
        assert not hp2.b.a, "Disabled during init (nested)"
        assert hp2.e
        assert hp2.a is not hp1.a
        assert hp2.b.parent is hp2
        assert hp2.b.b is hp1
        hp2.log.info("About to test a raised exception.")
        with pytest.raises(TraitError, match="already a parent."):
            hp2.set_trait("b", hp2)
        hp2_b = hp2.b
        hp2.set_trait("b", HPI())
        assert not hp2_b.parent, "hp2.parent should be removed when hp2 is replaced"
        assert await hp2.button.start() is True

        # Check replacement (validation)
        assert not hp2.parent, "No parent by default."
        hp1.set_trait("a", hp2)
        assert hp1.a is hp2, "hp1.a  replaced by hp2."
        assert hp2.parent is hp1, "When value is updated the parent is updated."

        assert not hp2.c.parent, "Tag specifying no parent succeeded."

        hp1.disable_ihp("a")
        assert not hp1.a, "Should have removed (hp2)"

        assert isinstance(hp2.e, ipw.Dropdown), "Spawning via instanceHP_wrapper inst."
        assert hp2.e.description == "From a factory"
        assert hp2.e.options == (1, 2, 3), "provided in defaults."
        hp2.disable_ihp("e")

    async def test_instance2(self, home: mb.Home):
        hp1 = HPI(name="hp1", a=None)
        # Check button
        hp1.my_button.click()
        await hp1.wait_tasks()
        assert hp1.clicked == 1, "Should have connected the button"
        assert hp1.box, "Loading children is debounced"
        await asyncio.sleep(0.1)  # ChildSetter.update is debounced
        assert hp1.my_button in hp1.box.children, "children for HBox_C should be added by a ChildSetter"
        b2 = ipw.Button()
        hp1.set_trait("my_button", b2)
        b2.click()
        await hp1.wait_tasks()
        assert hp1.clicked == 2, "Should have connected b2"
        await asyncio.sleep(0.1)
        assert b2 in hp1.box.children, "'set_children' with mode='monitor' should update box.children"

        # Test can regenerate
        assert not hp1.a
        hp1.enable_ihp("a")
        assert isinstance(hp1.a, HPI), "Re generated"

        # Test doesn't overload an existing value
        hp1_a = hp1.a
        hp1.enable_ihp("a")
        assert hp1_a is hp1.a
        hp2b = HPI2(home=home)
        # Test can load a more complex object & and close
        sr = hp2b.select_repository
        assert hp2b.select_repository.parent is hp2b
        sr.close()
        assert sr.closed
        assert not hp2b.trait_has_value("select_repository")
        assert hp2b.select_repository, "close should reset so default will load."
        assert not hp2b.select_repository.closed

    async def test_instancehp_union(self):
        class TestUnion(HasParent):
            union = InstanceHP(
                str | int,
                lambda _: 2,
                validate=lambda _, value: min(value, 10) if isinstance(value, int) else value,
                owner=cast(Self, 0),
            )

        obj = TestUnion()
        assert obj.union == 2
        with pytest.raises(TraitError, match="read-only"):
            obj.union = "abc"  # type: ignore
        assert obj.union == 2
        obj.set_trait("union", "abc")
        assert obj.union == "abc"
        obj.set_trait("union", 20)
        assert obj.union == 10, "by validation"

    async def test_instance_invalid_value(self):
        hpi3 = HPI3()
        with pytest.raises(
            TraitError,
            match="The 'hpi2' trait of a HPI3 instance expected an instance of `HPI2` or `None`, not the int 0.",
        ):
            hpi3.set_trait("hpi2", 0)

    async def test_instance_value_changed(self, home: mb.Home):
        hpi4 = HPI4(home=home)
        assert hpi4.hpi
        assert hpi4.value_changed["new"] is hpi4.hpi
        assert hpi4.value_changed["old"] is None
        old = hpi4.hpi
        new = HPI()
        hpi4.set_trait("hpi", new)
        assert hpi4.value_changed["new"] is new
        assert hpi4.value_changed["old"] is old

    @pytest.mark.parametrize("trait", ["box", "menubox", "hpi2"])
    async def test_instance_gc(self, trait, weakref_enabled):
        """Test that some objects will be automatically garbage collected.

        **Requires weakref_enabled.**
        """
        # ------------- WARNING --- -------------
        # DEBUGGING THIS TEST WILL LIKELY NOT WORK
        # Tip: pause at the assert to access the remaining referrers.

        hpi3 = HPI3()

        deleted = False

        def on_delete():
            nonlocal deleted
            deleted = True

        ref = weakref.ref(getattr(hpi3, trait))
        weakref.finalize(ref(), on_delete)
        hpi3.set_trait(trait, None)
        # ------- WARNING ------ : adding debug break points may cause this to fail.
        for _ in range(20):
            gc.collect()
            await asyncio.sleep(0.05)
            if deleted:
                break
            # Some objects schedule tasks against functions that may take a while to exit.
        assert deleted, (
            f"'{trait}' should be garbage collected after it is replaced. Referrers={gc.get_referrers(ref())}"
        )
