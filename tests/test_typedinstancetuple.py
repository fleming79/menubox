from typing import override

import ipywidgets as ipw
import pytest
import traitlets
from traitlets import Instance

import menubox as mb
import menubox.trait_types as tt

# ruff: noqa: PLR2004


class MenuboxSingleton(mb.MenuboxVT):
    SINGLETON_BY = ("cls", "name")


class VTT(mb.ValueTraits):
    change_count = traitlets.Int()
    added_count = traitlets.Int()
    removed_count = traitlets.Int()
    somelist_count = traitlets.Int()

    somelist = mb.TypedInstanceTuple(Instance(ipw.Text)).configure(
        update_by="description",
        update_item_names=("value",),
        set_parent=False,
        on_add="on_add",
        on_remove="on_remove",
    )
    menuboxvts: mb.TypedInstanceTuple[mb.MenuboxVT | MenuboxSingleton] = mb.TypedInstanceTuple(
        traitlets.Union((Instance(mb.MenuboxVT), Instance(MenuboxSingleton))),
    ).configure(
        update_by="name",
        update_item_names=("value",),
        set_parent=False,
        on_add="on_add",
        on_remove="on_remove",
        factory="_new_menubox",
    )

    @override
    def on_change(self, change: mb.ChangeType):
        assert isinstance(self, VTT)
        self.change_count += 1

    @traitlets.observe("somelist")
    def tuple_on_change(self, _):
        assert isinstance(self, VTT)
        self.somelist_count += 1

    def on_add(self, obj):
        self.added_count += 1

    def on_remove(self, obj):
        assert isinstance(obj, ipw.Text)
        self.removed_count += 1

    def _new_menubox(self, **kwargs):
        return mb.MenuboxVT(**kwargs)


class VTT1(VTT):
    removed_count = 0

    number = Instance(ipw.FloatText, ())

    def on_remove(self, obj):
        self.removed_count -= 10


class VTT2(mb.ValueTraits):
    value_traits_persist = tt.NameTuple("somelist", "somelist2")
    somelist = mb.TypedInstanceTuple(Instance(ipw.Text)).configure(
        update_by="description",
        spawn_new_instances=False,
        update_item_names=("value",),
    )
    somelist2 = mb.TypedInstanceTuple(traitlets.Union([Instance(VTT1), Instance(mb.Bunched)])).configure(
        factory="somelist2_factory",
        update_by="description",
        update_item_names=("value", "number.value"),
    )

    def somelist2_factory(self, **kwargs):
        return VTT1(**kwargs)


async def test_value_traits(home: mb.Home):
    assert len(VTT._vt_tit_names["menuboxvts"]["SINGLETON_BY"]()) == 2, "Registered at import"

    # Check registers working
    vals = ["update_by", "update_item_names", "new_update_inst", "trait", "SINGLETON_BY"]
    assert list(VTT._tuple_register("menuboxvts")) == vals
    assert VTT.get_tuple_singleton_by("menuboxvts") == ("cls", "name")

    vt = VTT(value_traits_persist=("somelist",), home=home)
    vt2 = VTT(parent=vt)
    assert isinstance(vt.home, mb.Home)
    assert vt2.home is vt.home

    item1 = ipw.Text(description="Item1")
    item2 = ipw.Text(description="Item2")

    assert vt.value() == {"somelist": ()}
    vt.somelist = (item1,)
    assert vt.change_count == 1
    assert vt.added_count == 1
    assert vt.somelist_count == 1
    assert str(vt.value()) == "{'somelist': (Text(value='', description='Item1'),)}"

    vt.somelist = (*vt.somelist, item2)
    assert vt.change_count == 2
    assert vt.added_count == 2
    assert vt.somelist_count == 2

    assert (item1, "value") in vt._vt_tuple_reg["somelist"].reg, "should be registered"
    item1.value = "a new value"
    assert vt.change_count == 3

    vt.somelist = (item2,)
    assert vt.change_count == 4
    assert vt.added_count == 2
    assert vt.removed_count == 1

    item1.value = "a removed item has changed should not be monitored anymore"
    assert vt.change_count == 4

    vt2.somelist = (item2,)
    assert vt2.change_count == 1
    assert vt2.added_count == 1
    item2.value = "item 2 should be monitored by both vt and vt2"
    assert vt.change_count == 5
    assert vt2.change_count == 2

    mb1: mb.MenuboxVT = vt2.get_tuple_obj("menuboxvts", add=False, name="mb1", home=vt2.home)
    assert mb1 not in vt2.menuboxvts, "Should not have added to tuple."
    vt2.menuboxvts = (mb1,)
    assert mb1 in vt2.menuboxvts, "Should have been added to tuple."
    assert mb1 is vt2.get_tuple_obj("menuboxvts", name="mb1")
    mb2 = vt2.get_tuple_obj("menuboxvts", name="mb2", home=home)
    assert mb2 is not mb1, "A new instance was expected with name='mb2'."
    assert mb2 in vt2.menuboxvts, "The new instance should be added."
    assert len(vt2.menuboxvts) == 2, "Both instances should be in tuple."

    vt11 = VTT1(home=vt.home)
    # Can also add directly using dict of key:value
    vt11.somelist = ({"description": "Added"},)  # type: ignore

    assert vt11.added_count == 1
    assert vt11.removed_count == 0
    assert vt11.change_count == 1

    vt11.somelist = ()
    assert vt11.change_count == 2
    assert vt11.removed_count == -10, "Should decrement by 10 each time"

    hhp2 = VTT2(home=vt11.home)
    with pytest.raises(RuntimeError):
        hhp2.somelist = ({"description": "never created"},)  # type: ignore
    assert len(hhp2.somelist) == 0

    hhp2.somelist = (ipw.Text(description="Is a member"),)
    assert len(hhp2.somelist) == 1
    assert not hhp2.somelist[0].value
    hhp2.somelist = ({"description": "Is a member", "value": "The value is updated"},)  # type: ignore
    assert isinstance(hhp2.somelist[0], ipw.Text)
    assert hhp2.somelist[0].value == "The value is updated"

    hhp2.somelist[0].value = "Another change"
    assert (
        str(hhp2.value()) == "{'somelist': (Text(value='Another change', description='Is a member'),), 'somelist2': ()}"
    )
    hhp2.value_traits_persist = ()
    assert not hhp2.value()

    # A test for multiple tuples in the same object
    assert len(hhp2._vt_tuple_reg["somelist"].reg) == 1
    hhp2.somelist2 = (vt11, mb.Bunched(key="value"))
    assert len(hhp2._vt_tuple_reg["somelist2"].reg) == 3
    assert vt11.parent is hhp2

    number = hhp2.somelist2[0].number
    assert (number, "value") in hhp2._vt_tuple_reg["somelist2"].reg

    number2 = ipw.FloatText()
    hhp2.somelist2[0].number = number2
    assert (number, "value") not in hhp2._vt_tuple_reg["somelist2"].reg, "stop observing"
    assert (number2, "value") in hhp2._vt_tuple_reg["somelist2"].reg
    assert len(hhp2._vt_tuple_reg["somelist2"].reg) == 3

    assert (vt11, "number") in hhp2._vt_tuple_reg["somelist2"].reg
    assert (vt11.number, "value") in hhp2._vt_tuple_reg["somelist2"].reg
    hhp2.somelist2 = ()
    assert len(hhp2._vt_tuple_reg["somelist2"].reg) == 0

    assert vt11.closed
