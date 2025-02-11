from __future__ import annotations

import asyncio
from typing import cast

import ipywidgets as ipw
import pytest

import menubox as mb
import menubox.trait_factory as tf
from menubox.hasparent import HasParent
from menubox.instance import InstanceHP, instanceHP_wrapper

Dropdown = instanceHP_wrapper(ipw.Dropdown, defaults={"options": [1, 2, 3]})


class HPI(mb.MenuBox):
    a = InstanceHP(cast(type["HPI"], "HPI"), name="a").configure(allow_none=True, on_replace_discontinue=True)
    b = InstanceHP(cast(type["HPI"], "HPI"), name="b").configure(load_default=False, allow_none=False)
    my_button = tf.Button(description="A button")
    box = tf.HBox().set_children("my_button", mode="monitor")
    clicked = 0

    async def button_clicked(self, b: ipw.Button):
        match b:
            case self.my_button:
                self.clicked = self.clicked + 1
            case _:
                await super().button_clicked(b)


class HPI2(HPI):
    b = InstanceHP(HPI, name="b").configure(
        on_replace_drop_parent=True, set_attrs={"name": lambda config: config["parent"].get_name(config)}
    )
    c = InstanceHP(HPI, name="C has value").configure(set_parent=False)
    d = InstanceHP(ipw.Dropdown).configure(dynamic_kwgs={"description": "c.name"}, allow_none=True)
    e = Dropdown(description="From a factory").configure(on_replace_discontinue=True, allow_none=True)
    select_repository = tf.SelectRepository()
    button = tf.AsyncRunButton(cfunc="_button_async")
    widgetlist = mb.StrTuple("select_repository", "not a widget")
    box_widgets = tf.Box().configure(
        dlink={
            "source": ("self", "widgetlist"),
            "target": "children",
            "transform": "lambda val:tuple(parent.get_widgets(val))",
        }
    )

    @staticmethod
    def get_name(config: tf.IHPConfig):
        return f"{config['parent']}.{config['name']}"

    async def _button_async(self):
        return True


async def test_instance():
    with pytest.raises(ValueError, match="`parent`is an invalid argument. Use the `set_parent` tag instead."):
        InstanceHP(HPI, parent=None)

    hp1 = HPI()
    assert hp1.my_button
    assert hp1.a.name
    hp1.parent = None
    # Spawn from Class name
    assert isinstance(hp1.a, HPI)
    with pytest.raises(RuntimeError):
        assert not hp1.b, "Tag load_default=False & allow_none=False"
    assert hp1.a.name == "a"
    assert hp1.a.parent is hp1

    hp2 = HPI2(a=None, b={"b": hp1, "a": None})  # Can override values during __init__
    assert not hp2.a, "Disabled during init"
    assert not hp2.b.a, "Disabled during init (nested)"
    assert hp2.e
    assert hp2.a is not hp1.a
    assert isinstance(hp2.b, HasParent)
    assert hp2.b.parent
    hp2.log.info("About to test a raised exception.")
    with pytest.raises(RuntimeError, match="already a parent."):
        hp2.set_trait("b", hp2)
    assert hp2.b.name == "<HPI2 name:''>.b", "by `get_name`."
    hp2_b = hp2.b
    hp2.set_trait("b", HPI())
    assert not hp2_b.parent, "Tag on_replace_drop_parent should be respected."
    assert await hp2.button.start() is True
    assert hp2.select_repository in hp2.box_widgets.children, "using dlink with a lambda transform"

    # Check button
    hp1.my_button.click()
    await hp1.wait_tasks()
    assert hp1.clicked == 1, "Should have connected the button"
    assert hp1.box, "Loading children is debounced"
    assert hp1.my_button in hp1.box.children, 'children for HBox_C added with "get_widgets"'
    b2 = ipw.Button()
    hp1.set_trait("my_button", b2)
    b2.click()
    await hp1.wait_tasks()
    assert hp1.clicked == 2, "Should have connected b2"
    assert b2 in hp1.box.children, "'set_children' with mode='monitor' should update box.children"

    # Check replacement (validation)
    assert not hp2.parent, "No parent by default."
    hp_a_original = hp1.a
    hp1.set_trait("a", hp2)
    assert hp1.a is hp2, "hp1.a  replaced by hp2."
    assert hp2.parent is hp1, "When value is updated the parent is updated."
    assert hp_a_original.parent is hp1, "parent should be retained."

    await asyncio.sleep(1)
    assert hp_a_original.discontinued, "Tag specifies it should be discontinued."
    assert not hp2.c.parent, "Tag specifying no parent succeeded."
    assert hp2.d.description == "C has value", "from dynamic_kwgs."

    hp1.instanceHP_enable_disable("a", False)
    assert not hp1.a, "Should have removed (hp2)"
    await asyncio.sleep(1)
    assert hp2.discontinued

    assert isinstance(hp2.d, ipw.Dropdown), "Spawning a widget."
    assert isinstance(hp2.e, ipw.Dropdown), "Spawning via instanceHP_wrapper inst."
    assert hp2.e.description == "From a factory"
    assert hp2.e.options == (1, 2, 3), "provided in defaults."
    hp2_e = hp2.e
    hp2.instanceHP_enable_disable("e", False)

    await asyncio.sleep(1)
    assert not hp2_e.comm, "Comm is set to None when `close` is called."

    # Test can regenerate
    assert not hp1.a
    hp1.instanceHP_enable_disable("a", True, overrides={"a": None})
    assert isinstance(hp1.a, HPI), "Re generated"
    assert not hp1.a.a, "From overrides is disabled"

    # Test doesn't overload an existing value
    hp1_a = hp1.a
    hp1.instanceHP_enable_disable("a", True)
    assert hp1_a is hp1.a
    hp2b = HPI2()
    # Test can load a more complex object & and discontinue
    assert hp2b.select_repository.repository.root
    assert hp2b.select_repository.parent is hp2b
    assert hp2b.select_repository._ptname == "select_repository"
    sr = hp2b.select_repository
    sr.discontinue()
    assert sr.discontinued
    assert not hp2b.trait_has_value("select_repository")
    assert hp2b.select_repository, "Discontinue should reset so default will load."
    assert not hp2b.select_repository.discontinued
