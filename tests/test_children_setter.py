from __future__ import annotations

from typing import Self, cast

import anyio
import ipywidgets as ipw
import pytest

import menubox as mb
from menubox.children_setter import ChildrenSetter
from menubox.trait_factory import TF


class ChildrenSetterTesterNestedObj(mb.MenuboxVT):
    views = TF.ViewDict(
        cast("Self", 0),
        {
            "view a": lambda _: (ipw.Button(description="Button"), ipw.HTML("HTML")),
            "view b": lambda p: (p.button, p.dropdown),
        },
    )
    button = TF.Button(description="nested button")
    dropdown = TF.Dropdown(cast("Self", 0), description="nested dropdown").configure(TF.IHPMode.XLRN)
    label = TF.Label(cast("Self", 0), value="Nested Label")


class ChildrenSetterTester(mb.MenuboxVT):
    dropdown = TF.Dropdown(cast("Self", 0), description="dropdown")
    label = TF.Label(cast("Self", 0), value="Label")
    dd_no_default = TF.Dropdown(cast("Self", 0), description="Label no default").configure(TF.IHPMode.X_RN)
    nested = TF.InstanceHP(klass=ChildrenSetterTesterNestedObj).configure(TF.IHPMode.XLRN)
    nested_always = TF.InstanceHP(klass=ChildrenSetterTesterNestedObj)
    dynamic_box = TF.Box(cast("Self", 0)).hooks(
        set_children=lambda p: (p.dd_no_default, p.dropdown, p.nested.dropdown, p.nested.button),  # pyright: ignore[reportOptionalMemberAccess]
    )
    plain_box = TF.Box(cast("Self", 0))


@pytest.mark.parametrize(
    "dottednames",
    [
        ("dropdown", "label"),
        ("nested.button", "nested.dropdown", "nested.label"),
    ],
)
async def test_children_setter_manual(dottednames: tuple):
    cto = ChildrenSetterTester()
    cs = ChildrenSetter(parent=cto, name="plain_box", children=lambda _: dottednames)
    await cs.wait_tasks()
    widgets = tuple(cto.get_widgets(dottednames))
    await cs.wait_tasks()
    assert cto.plain_box.children == widgets


async def test_children_setter_nested_enable_disable() -> None:
    cto = ChildrenSetterTester()
    dottednames = ("dropdown", "nested.button", "nested.dropdown")
    cs = ChildrenSetter(parent=cto, name="plain_box", children=lambda _: dottednames)
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
    await anyio.sleep(0.002)
    assert cto.nested
    assert cto.dynamic_box.children == (
        cto.dropdown,
        cto.nested.dropdown,
        cto.nested.button,
    )
    assert cto.dynamic_box.layout.visibility == "visible"
    for c in cto.dynamic_box.children:
        mb.utils.hide(c)
    await anyio.sleep(0.02)
    assert not cto.dynamic_box.children
    assert cto.dynamic_box.layout.visibility == "hidden"


async def test_children_setter_enable():
    cto = ChildrenSetterTester()
    assert cto.dynamic_box
    cto.enable_ihp("dd_no_default")
    await anyio.sleep(0.02)
    assert cto.nested
    assert cto.dynamic_box.children == (cto.dd_no_default, cto.dropdown, cto.nested.dropdown, cto.nested.button)


async def test_children_setter_hide():
    cto = ChildrenSetterTester()
    assert cto.dynamic_box
    cs = ChildrenSetter(parent=cto, name="dynamic_box")
    assert cs.tasks
    assert cs._dottednames == ("dd_no_default", "dropdown", "nested.dropdown", "nested.button")
    mb.utils.hide(cto.dropdown)
    await cs.wait_tasks()
    assert cto.nested
    assert cto.dynamic_box.children == (cto.nested.dropdown, cto.nested.button)
    mb.utils.unhide(cto.dropdown)
    await cs.wait_tasks()
    assert cto.dynamic_box.children == (cto.dropdown, cto.nested.dropdown, cto.nested.button)


async def test_children_setter_showbox_link():
    class ChildrenSetterTesterShowboxLink(mb.MenuboxVT):
        my_tuple = mb.InstanceHPTuple(mb.Menubox)
        box = TF.VBox(cast("Self", 0)).hooks(set_children=(lambda p: p.my_tuple, {"set_showbox": True}))

    cb = ChildrenSetterTesterShowboxLink()
    b1 = cb.get_tuple_obj(lambda p: p.my_tuple, name="b1")
    assert cb.box
    assert b1.showbox
    assert b1 in cb.my_tuple
    b2 = cb.get_tuple_obj(lambda p: p.my_tuple, name="b2")
    b3 = cb.get_tuple_obj(lambda p: p.my_tuple, name="b3")
    assert cb.my_tuple == (b1, b2, b3)
    await cb

    # promote
    assert b3.button_promote
    await b3.button_clicked(b3.button_promote)
    assert cb.my_tuple == (b1, b3, b2)

    # demote
    assert b3.button_demote
    await b3.button_clicked(b3.button_demote)
    await b3
    assert cb.my_tuple == (b1, b2, b3)

    # exit
    b2.enable_ihp(lambda p: p.button_exit)
    assert b2.button_exit
    await b2.button_clicked(b2.button_exit)
    assert cb.my_tuple == (b1, b3)
