from __future__ import annotations

import asyncio

import ipywidgets as ipw
import pytest
import traitlets

import menubox as mb
from menubox import trait_factory as tf
from menubox import utils
from menubox.children_setter import ChildrenSetter
from menubox.trait_types import NameTuple


class ChildrenSetterTesterNestedObj(mb.MenuboxVT):
    views = traitlets.Dict(
        {
            "view a": lambda: (ipw.Button(description="Button"), ipw.HTML("HTML")),
            "view b": ("button", "dropdown"),
        }
    )
    button = tf.Button_main(description="nested button")
    dropdown = tf.Dropdown(description="nested dropdown").configure(allow_none=True)
    label = tf.Label("Nested Label")


class ChildrenSetterTester(mb.MenuboxVT):
    dropdown = tf.Dropdown(description="dropdown")
    label = tf.Label("Label")
    dd_no_default = tf.Dropdown(description="Label no default").configure(load_default=False)
    nested = tf.InstanceHP(ChildrenSetterTesterNestedObj).configure(allow_none=True)
    dynamic_box = tf.Box().hooks(
        set_children={
            "mode": "monitor",
            "dottednames": ("dd_no_default", "dropdown", "nested.dropdown", "nested.button"),
        },
    )
    dynamic_box_nametuple_children = NameTuple("label")
    dynamic_box_nametuple = tf.Box().hooks(
        set_children={
            "mode": "monitor_nametuple",
            "nametuple_name": "dynamic_box_nametuple_children",
        },
    )
    plain_box = tf.Box()


@pytest.fixture
async def cto(home: mb.Home):
    return ChildrenSetterTester(home=home)


@pytest.mark.parametrize(
    "dottednames",
    [
        ("dropdown", "label"),
        ("nested.button", "nested.dropdown", "nested.label"),
    ],
)
async def test_children_setter_manual(cto: ChildrenSetterTester, dottednames: tuple):
    children_setter = ChildrenSetter(parent=cto, name="plain_box", dottednames=dottednames)
    await children_setter.wait_tasks()
    assert children_setter.dottednames == dottednames
    widgets = tuple(cto.get_widgets(dottednames))
    assert cto.plain_box.children == widgets


async def test_children_setter_nested_enable_disable(cto: ChildrenSetterTester):
    dottednames = ("dropdown", "nested.button", "nested.dropdown")
    cs = ChildrenSetter(parent=cto, name="plain_box", dottednames=dottednames)
    await cs.wait_tasks()
    widgets = tuple(cto.get_widgets(dottednames))
    assert cto.plain_box.children == widgets

    # check disable nested
    cto.set_trait("nested", None)
    assert all(b.comm is None for b in widgets[1:]), "Nested widgets should be closed"
    assert cs.tasks, "Update debounced should be scheduled"
    await cs.wait_tasks()
    assert cto.plain_box.children == (cto.dropdown,)

    # Check enable nested
    cto.enable_widget("nested", {"dropdown": None})
    assert cto.nested
    assert cto.nested.dropdown is None
    assert cs.tasks, "Update debounced should be scheduled"
    await cs.wait_tasks()
    widgets = tuple(cto.get_widgets(dottednames))
    assert cto.plain_box.children == widgets

    cto.close()
    assert cs.closed, "Closing the parent should close it."


async def test_children_setter_builtin(cto: ChildrenSetterTester):
    assert cto.dynamic_box
    await asyncio.sleep(0.1)
    assert cto.nested
    assert cto.dynamic_box.children == (cto.dropdown, cto.nested.dropdown, cto.nested.button)


async def test_children_setter_enable(cto: ChildrenSetterTester):
    assert cto.dynamic_box
    cto.enable_widget("dd_no_default")
    await asyncio.sleep(0.1)
    assert cto.nested
    assert cto.dynamic_box.children == (cto.dd_no_default, cto.dropdown, cto.nested.dropdown, cto.nested.button)


async def test_children_setter_hide(cto: ChildrenSetterTester):
    assert cto.dynamic_box
    mb.utils.hide(cto.dropdown)
    await asyncio.sleep(0.1)
    assert cto.nested
    assert cto.dynamic_box.children == (cto.nested.dropdown, cto.nested.button)


async def test_children_setter_nametuple(cto: ChildrenSetterTester):
    assert cto.dynamic_box_nametuple
    await asyncio.sleep(0.1)
    assert cto.dynamic_box_nametuple.children == (cto.label,)

    # Check we can dynamically adjust the children
    cto.dynamic_box_nametuple_children = ("label", "dropdown", "nested.dropdown", "nested.button")
    await asyncio.sleep(0.1)
    assert cto.nested
    assert cto.dynamic_box_nametuple.children == (cto.label, cto.dropdown, cto.nested.dropdown, cto.nested.button)

    # Check still dynamically updates
    utils.hide(cto.dropdown)
    await asyncio.sleep(0.1)
    assert cto.dynamic_box_nametuple.children == (cto.label, cto.nested.dropdown, cto.nested.button)
