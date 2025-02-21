from __future__ import annotations

import asyncio

import ipywidgets as ipw
import pytest
import traitlets

import menubox as mb
from menubox import trait_factory as tf
from menubox.children_setter import ChildrenSetter


class ChildrenSetterTesterNestedObj(mb.MenuBoxVT):
    views = traitlets.Dict(
        {
            "view a": lambda: (ipw.Button(description="Button"), ipw.HTML("HTML")),
            "view b": ("button", "dropdown"),
        }
    )
    button = tf.Button(description="nested button")
    dropdown = tf.Dropdown(description="nested dropdown").configure(allow_none=True)


class ChildrenSetterTester(mb.MenuBoxVT):
    dropdown = tf.Dropdown(description="dropdown")
    label = tf.Label("Label")
    label_no_default = tf.Label("Label no default").configure(load_default=False)
    nested = tf.InstanceHP(ChildrenSetterTesterNestedObj).configure(allow_none=True)
    dynamic_box = tf.Box().configure(
        children={
            "mode": "monitor",
            "dottednames": ("label_no_default", "dropdown", "nested.dropdown", "nested.button"),
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
        ("nested.button", "nested.dropdown"),
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
    children_setter = ChildrenSetter(parent=cto, name="plain_box", dottednames=dottednames)
    await children_setter.wait_tasks()
    widgets = tuple(cto.get_widgets(dottednames))
    assert cto.plain_box.children == widgets

    # check disable nested
    cto.set_trait("nested", None)
    assert all(b.comm is None for b in widgets[1:]), "Nested widgets should be closed"
    assert children_setter.tasks, "Update debounced should be scheduled"
    await children_setter.wait_tasks()
    assert cto.plain_box.children == (cto.dropdown,)

    # Check enable nested
    cto.enable_widget("nested", {"dropdown": None})
    assert cto.nested.dropdown is None
    assert children_setter.tasks, "Update debounced should be scheduled"
    await children_setter.wait_tasks()
    widgets = tuple(cto.get_widgets(dottednames))
    assert cto.plain_box.children == widgets


async def test_children_setter_builtin(cto: ChildrenSetterTester):
    assert cto.dynamic_box
    await asyncio.sleep(0.1)
    assert cto.dynamic_box.children == (cto.dropdown, cto.nested.dropdown, cto.nested.button)


async def test_children_setter_enable(cto: ChildrenSetterTester):
    assert cto.dynamic_box
    cto.enable_widget("label_no_default")
    await asyncio.sleep(0.1)
    assert cto.dynamic_box.children == (cto.label_no_default, cto.dropdown, cto.nested.dropdown, cto.nested.button)


async def test_children_setter_hide(cto: ChildrenSetterTester):
    assert cto.dynamic_box
    mb.utils.hide(cto.dropdown)
    await asyncio.sleep(0.1)
    assert cto.dynamic_box.children == (cto.nested.dropdown, cto.nested.button)
