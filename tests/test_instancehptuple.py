from typing import Self, override

import ipywidgets as ipw
import pytest
import traitlets
from traitlets import Instance

import menubox as mb
import menubox.instancehp_tuple
import menubox.trait_types as tt
from menubox.instance import IHPSet

# ruff: noqa: PLR2004


class MenuboxSingleton(mb.HasHome, mb.MenuboxVT):
    SINGLE_BY = ("home", "name")


class VTT(mb.ValueTraits):
    change_count = traitlets.Int()
    added_count = traitlets.Int()
    removed_count = traitlets.Int()
    somelist_count = traitlets.Int()

    somelist = menubox.instancehp_tuple.InstanceHPTuple[Self, ipw.Text](Instance(ipw.Text)).hooks(
        update_by="description",
        update_item_names=("value",),
        set_parent=False,
        on_add=lambda c: c["parent"].on_add(c),
        on_remove=lambda c: c["parent"].on_remove(c),
    )
    menuboxvts = menubox.instancehp_tuple.InstanceHPTuple[Self, mb.MenuboxVT | MenuboxSingleton](
        traitlets.Union((Instance(mb.MenuboxVT), Instance(MenuboxSingleton))),
        klass=mb.MenuboxVT,
        factory=lambda c: c["parent"]._new_menubox(**c["kwgs"]),
    ).hooks(
        update_by="name",
        update_item_names=("value",),
        set_parent=False,
        on_add=lambda c: c["parent"].on_add(c),
        on_remove=lambda c: c["parent"].on_remove(c),
    )

    @override
    def on_change(self, change: mb.ChangeType):
        assert isinstance(self, VTT)
        self.change_count += 1

    @traitlets.observe("somelist")
    def tuple_on_change(self, _):
        assert isinstance(self, VTT)
        self.somelist_count += 1

    def on_add(self, c: IHPSet):
        self.added_count += 1

    def on_remove(self, c: IHPSet):
        self.removed_count += 1

    def _new_menubox(self, **kwargs):
        return mb.MenuboxVT(**kwargs)


class VT(VTT):
    removed_count = 0

    number = Instance(ipw.FloatText, ())

    def on_remove(self, c: IHPSet):
        self.removed_count -= 10


class VTT2(mb.ValueTraits):
    value_traits_persist = tt.NameTuple("somelist", "somelist2")
    somelist = menubox.instancehp_tuple.InstanceHPTuple(Instance(ipw.Text), factory=None).hooks(
        update_by="description",
        update_item_names=("value",),
    )
    somelist2 = menubox.instancehp_tuple.InstanceHPTuple[Self, VT | mb.Bunched](
        traitlets.Union([Instance(VT), Instance(mb.Bunched)]),
        klass=mb.MenuboxVT,
        factory=lambda c: c["parent"].somelist2_factory(**c["kwgs"]),
    ).hooks(update_by="description", update_item_names=("value", "number.value"), set_parent=True, close_on_remove=True)

    def somelist2_factory(self, **kwargs):
        return VT(**kwargs)


class TestValueTraits:
    async def test_registration_and_singleton(self):
        # Test registration and singleton behavior
        assert isinstance(VTT._InstanceHPTuple.get("menuboxvts"), menubox.instancehp_tuple.InstanceHPTuple)

    async def test_basic_functionality(self):
        # Test basic ValueTraits and InstanceHPTuple functionality
        vt = VTT(value_traits_persist=("somelist",))
        vt2 = VTT(parent=vt)

        item1 = ipw.Text(description="Item1")
        item2 = ipw.Text(description="Item2")

        assert vt.value() == {"somelist": ()}
        vt.somelist = (item1,)
        assert vt.change_count == 2
        assert vt.added_count == 1
        assert vt.somelist_count == 2
        assert str(vt.value()) == "{'somelist': (Text(value='', description='Item1'),)}"

        vt.somelist = (*vt.somelist, item2)
        assert vt.change_count == 3
        assert vt.added_count == 2
        assert vt.somelist_count == 3

        assert (item1, "value") in vt._vt_tuple_reg["somelist"].reg, "should be registered"
        item1.value = "a new value"
        assert vt.change_count == 4

        vt.somelist = (item2,)
        assert vt.change_count == 5
        assert vt.added_count == 2
        assert vt.removed_count == 1

        item1.value = "a removed item has changed should not be monitored anymore"
        assert vt.change_count == 5

        vt2.somelist = (item2,)
        assert vt2.change_count == 0, "Value traits should only emit when being monitored"
        vt2.add_value_traits("somelist")
        assert vt2.added_count == 1
        item2.value = "item 2 should be monitored by both vt and vt2"
        assert vt.change_count == 6
        assert vt2.change_count == 1

    async def test_tuple_obj_and_singleton(self, home: mb.Home):
        vt = VTT(value_traits_persist=("somelist",))
        vt2 = VTT(parent=vt)
        # Test get_tuple_obj and singleton behavior with InstanceHPTuple
        mb1: mb.MenuboxVT = vt2.get_tuple_obj("menuboxvts", add=False, name="mb1")
        assert mb1 not in vt2.menuboxvts, "Should not have added to tuple."
        vt2.menuboxvts = (mb1,)
        assert mb1 in vt2.menuboxvts, "Should have been added to tuple."
        assert mb1 is vt2.get_tuple_obj("menuboxvts", name="mb1")
        mb2 = MenuboxSingleton(name="mb2", home=home)
        vt2.menuboxvts = (mb1, mb2)
        assert mb2 is not mb1, "A new instance was expected with name='mb2'."
        assert mb2 in vt2.menuboxvts, "The new instance should be added."
        assert len(vt2.menuboxvts) == 2, "Both instances should be in tuple."

    async def test_subclassing_and_on_remove(self):
        # Test subclassing ValueTraits and on_remove
        vt = VT(value_traits_persist=("somelist",))
        vt.somelist = ({"description": "Added"},)  # type: ignore

        assert vt.added_count == 1
        assert vt.removed_count == 0
        assert vt.change_count == 2

        vt.somelist = ()
        assert vt.change_count == 3
        assert vt.removed_count == -10, "Should decrement by 10 each time"

    async def test_spawn_new_instances(self):
        # Test InstanceHPTuple with factory=None
        hhp2 = VTT2()
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
            str(hhp2.value())
            == "{'somelist': (Text(value='Another change', description='Is a member'),), 'somelist2': ()}"
        )
        hhp2.value_traits_persist = ()
        assert not hhp2.value()

    async def test_multiple_tuples_and_nested_updates(self):
        vt1 = VT()
        vt2 = VTT2()
        # Test multiple tuples in the same object and nested trait updates
        vt2.somelist = (ipw.Text(),)
        assert len(vt2._vt_tuple_reg["somelist"].reg) == 1
        vt2.somelist2 = (vt1, mb.Bunched(key="value"))
        assert len(vt2._vt_tuple_reg["somelist2"].reg) == 3
        assert vt1.parent is vt2

        number = vt2.somelist2[0].number
        assert (number, "value") in vt2._vt_tuple_reg["somelist2"].reg

        number2 = ipw.FloatText()
        vt2.somelist2[0].number = number2
        assert (number, "value") not in vt2._vt_tuple_reg["somelist2"].reg, "stop observing"
        assert (number2, "value") in vt2._vt_tuple_reg["somelist2"].reg
        assert len(vt2._vt_tuple_reg["somelist2"].reg) == 3

        assert (vt1, "number") in vt2._vt_tuple_reg["somelist2"].reg
        assert (vt1.number, "value") in vt2._vt_tuple_reg["somelist2"].reg
        vt2.somelist2 = ()
        assert len(vt2._vt_tuple_reg["somelist2"].reg) == 0

        assert vt1.closed

    async def test_removal_on_close(self):
        vt = VTT(value_traits_persist=("somelist",))
        item1 = ipw.Text(description="Item1")
        vt.somelist = (item1,)
        assert len(vt.somelist) == 1
        item1.close()
        assert len(vt.somelist) == 0
