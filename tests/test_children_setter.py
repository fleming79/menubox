from __future__ import annotations

from typing import Self, cast

import anyio
import ipywidgets as ipw
import pytest

import menubox as mb
from menubox import utils
from menubox.children_setter import ChildrenSetter
from menubox.trait_factory import TF
from menubox.trait_types import NameTuple


class ChildrenSetterTesterNestedObj(mb.MenuboxVT):
    views = TF.ViewDict(
        cast(Self, 0),
        {
            "view a": lambda _: (ipw.Button(description="Button"), ipw.HTML("HTML")),
            "view b": lambda p: (p.button, p.dropdown),
        },
    )
    button = TF.Button(description="nested button")
    dropdown = TF.Dropdown(description="nested dropdown").configure(TF.IHPMode.XLRN)
    label = TF.Label(value="Nested Label")


class ChildrenSetterTester(mb.MenuboxVT):
    dropdown = TF.Dropdown(description="dropdown")
    label = TF.Label(value="Label")
    dd_no_default = TF.Dropdown(description="Label no default").configure(TF.IHPMode.X_RN)
    nested = TF.InstanceHP(klass=ChildrenSetterTesterNestedObj).configure(TF.IHPMode.XLRN)
    dynamic_box = TF.Box().hooks(
        set_children={
            "mode": "monitor",
            "dottednames": ("dd_no_default", "dropdown", "nested.dropdown", "nested.button"),
        },
    )
    dynamic_box_nametuple_children = NameTuple("label")
    dynamic_box_nametuple = TF.Box().hooks(
        set_children={
            "mode": "monitor_nametuple",
            "nametuple_name": "dynamic_box_nametuple_children",
        },
    )
    plain_box = TF.Box()


@pytest.mark.parametrize(
    "dottednames",
    [
        ("dropdown", "label"),
        ("nested.button", "nested.dropdown", "nested.label"),
    ],
)
async def test_children_setter_manual(dottednames: tuple):
    cto = ChildrenSetterTester()
    children_setter = ChildrenSetter(parent=cto, name="plain_box", dottednames=dottednames)
    await children_setter.wait_tasks()
    assert children_setter.dottednames == dottednames
    widgets = tuple(cto.get_widgets(dottednames))
    await children_setter.wait_tasks()
    assert cto.plain_box.children == widgets


async def test_children_setter_nested_enable_disable() -> None:
    cto = ChildrenSetterTester()
    dottednames = ("dropdown", "nested.button", "nested.dropdown")
    cs = ChildrenSetter(parent=cto, name="plain_box", dottednames=dottednames)
    await cs.wait_tasks()
    widgets = tuple(cto.get_widgets(dottednames))
    await cs.wait_tasks()
    assert cto.plain_box.children == widgets

    # check disable nested
    cto.set_trait("nested", None)
    assert all(b.comm is None for b in widgets[1:]), "Nested widgets should be closed"
    assert cs.tasks, "Update debounced should be scheduled"
    await cs.wait_tasks()
    assert cto.plain_box.children == (cto.dropdown,)

    # Check enable nested
    cto.enable_ihp("nested", override={"dropdown": None})
    assert cto.nested
    assert cto.nested.dropdown is None
    assert cs.tasks, "Update debounced should be scheduled"
    await cs.wait_tasks()
    widgets = tuple(cto.get_widgets(dottednames))
    assert cto.plain_box.children == widgets

    cto.close()
    assert cs.closed, "Closing the parent should close it."


async def test_children_setter_builtin():
    cto = ChildrenSetterTester()
    assert cto.dynamic_box
    await anyio.sleep(0.1)
    assert cto.nested
    assert cto.dynamic_box.children == (cto.dropdown, cto.nested.dropdown, cto.nested.button)


async def test_children_setter_enable():
    cto = ChildrenSetterTester()
    assert cto.dynamic_box
    cto.enable_ihp("dd_no_default")
    await anyio.sleep(0.1)
    assert cto.nested
    assert cto.dynamic_box.children == (cto.dd_no_default, cto.dropdown, cto.nested.dropdown, cto.nested.button)


async def test_children_setter_hide():
    cto = ChildrenSetterTester()
    assert cto.dynamic_box
    mb.utils.hide(cto.dropdown)
    await anyio.sleep(0.1)
    assert cto.nested
    assert cto.dynamic_box.children == (cto.nested.dropdown, cto.nested.button)


async def test_children_setter_nametuple():
    cto = ChildrenSetterTester()
    assert cto.dynamic_box_nametuple
    await anyio.sleep(0.1)
    assert cto.dynamic_box_nametuple.children == (cto.label,)

    # Check we can dynamically adjust the children
    cto.dynamic_box_nametuple_children = ("label", "dropdown", "nested.dropdown", "nested.button")
    await anyio.sleep(0.1)
    assert cto.nested
    assert cto.dynamic_box_nametuple.children == (cto.label, cto.dropdown, cto.nested.dropdown, cto.nested.button)

    # Check still dynamically updates
    utils.hide(cto.dropdown)
    await anyio.sleep(0.1)
    assert cto.dynamic_box_nametuple.children == (cto.label, cto.nested.dropdown, cto.nested.button)
