from __future__ import annotations

import asyncio
import gc
import weakref
from typing import cast

import ipywidgets as ipw
import pytest
from traitlets import Dict, TraitError

import menubox as mb
import menubox.trait_factory as tf
from menubox.hasparent import HasParent
from menubox.instance import IHPChange, InstanceHP, instanceHP_wrapper

Dropdown = instanceHP_wrapper(ipw.Dropdown, defaults={"options": [1, 2, 3]})


class HPI(mb.MenuBox):
    a = InstanceHP(cast(type["HPI"], "tests.test_instance.HPI"), name="a").configure(allow_none=True)
    b = InstanceHP(cast(type["HPI"], "tests.test_instance.HPI"), name="b").configure(
        load_default=False, allow_none=False
    )
    my_button = tf.Button(description="A button")
    box = tf.HBox().configure(children={"dottednames": ("my_button",), "mode": "monitor"})
    clicked = 0

    async def button_clicked(self, b: ipw.Button):
        match b:
            case self.my_button:
                self.clicked = self.clicked + 1
            case _:
                await super().button_clicked(b)


class HPI2(HPI, mb.MenuBoxVT):
    b = InstanceHP(HPI, name="b").configure(set_attrs={"name": lambda config: config["parent"].get_name(config)})
    c = InstanceHP(HPI, name="C has value").configure(set_parent=False)
    d = InstanceHP(ipw.Dropdown).configure(dynamic_kwgs={"description": "c.name"}, allow_none=True)
    e = Dropdown(description="From a factory").configure(allow_none=True)
    select_repository = tf.SelectRepository()
    button = tf.AsyncRunButton(cfunc="_button_async")
    widgetlist = mb.StrTuple("select_repository", "not a widget")

    @staticmethod
    def get_name(config: tf.IHPCreate):
        return f"{config['parent']}.{config['name']}"

    async def _button_async(self):
        return True


class HPI3(mb.MenuBox):
    box = tf.Box().configure(allow_none=True)
    menubox = tf.MenuBox(views={"main": None}).configure(allow_none=True)
    hpi2 = tf.InstanceHP(HPI2).configure(allow_none=True)


class HPI4(HasParent):
    hpi = tf.InstanceHP(HPI).configure(
        allow_none=True,
        change_new=lambda change: change["parent"].set_trait("change_new", change),
        change_old=lambda change: change["parent"].set_trait("change_old", change),
    )
    change_new = Dict()
    change_old = Dict()


async def test_instance(home: mb.Home):
    with pytest.raises(ValueError, match="`parent`is an invalid argument. Use the `set_parent` tag instead."):
        InstanceHP(HPI, parent=None)

    hp1 = HPI(name="hp1")
    assert hp1.my_button
    assert hp1.a.name
    hp1.parent = None
    # Spawn from Class name
    assert isinstance(hp1.a, HPI)
    with pytest.raises(RuntimeError):
        assert not hp1.b, "Tag load_default=False & allow_none=False"
    assert hp1.a.name == "a"
    assert hp1.a.parent is hp1

    hp2 = HPI2(a=None, b={"b": hp1, "a": None}, home=home)  # Can override values during __init__
    assert not hp2.a, "Disabled during init"
    assert not hp2.b.a, "Disabled during init (nested)"
    assert hp2.e
    assert hp2.a is not hp1.a
    assert isinstance(hp2.b, HasParent)
    assert hp2.b.parent is hp2
    assert hp2.b.name == "<HPI2 name:''>.b", "by `get_name`."
    assert hp2.b.b is hp1
    hp2.log.info("About to test a raised exception.")
    with pytest.raises(RuntimeError, match="already a parent."):
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
    assert hp2.d.description == "C has value", "from dynamic_kwgs."

    hp1.instanceHP_enable_disable("a", False)
    assert not hp1.a, "Should have removed (hp2)"

    assert isinstance(hp2.d, ipw.Dropdown), "Spawning a widget."
    assert isinstance(hp2.e, ipw.Dropdown), "Spawning via instanceHP_wrapper inst."
    assert hp2.e.description == "From a factory"
    assert hp2.e.options == (1, 2, 3), "provided in defaults."
    hp2.instanceHP_enable_disable("e", False)


async def test_instance2(home: mb.Home):
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
    hp1.instanceHP_enable_disable("a", {"a": None})
    assert isinstance(hp1.a, HPI), "Re generated"
    assert not hp1.a.a, "From overrides is disabled"

    # Test doesn't overload an existing value
    hp1_a = hp1.a
    hp1.instanceHP_enable_disable("a", True)
    assert hp1_a is hp1.a
    hp2b = HPI2(home=home)
    # Test can load a more complex object & and close
    assert hp2b.select_repository.repository.root
    assert hp2b.select_repository.parent is hp2b
    sr = hp2b.select_repository
    sr.close()
    assert sr.closed
    assert not hp2b.trait_has_value("select_repository")
    assert hp2b.select_repository, "close should reset so default will load."
    assert not hp2b.select_repository.closed


async def test_instance_invalid_value():
    hpi3 = HPI3()
    with pytest.raises(
        TraitError, match="The 'hpi2' trait of a HPI3 instance expected an instance of `HPI2` or `None`, not the int 0."
    ):
        hpi3.set_trait("hpi2", 0)


async def test_instance_change():
    hpi4 = HPI4()
    assert hpi4.hpi
    assert hpi4.change_new == IHPChange(name="hpi", parent=hpi4, obj=hpi4.hpi)
    old = hpi4.hpi
    new = HPI()
    hpi4.set_trait("hpi", new)
    assert str(hpi4.change_new) == str(IHPChange(name="hpi", parent=hpi4, obj=new))
    assert str(hpi4.change_old) == str(IHPChange(name="hpi", parent=hpi4, obj=old))


@pytest.mark.parametrize("trait", ["box", "menubox", "hpi2"])
async def test_instance_gc(trait, weakref_enabled):  # noqa: ARG001
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
    assert deleted, f"'{trait}' should be garbage collected after it is replaced. Referrers={gc.get_referrers(ref())}"
