from typing import Self, override

import ipywidgets as ipw
import pytest
import traitlets
from ipylab.common import Fixed

import menubox
from menubox import HasParent, ValueTraits
from menubox.trait_factory import TF
from menubox.trait_types import NameTuple


class Nested(HasParent):
    number = TF.InstanceHP(klass=ipw.FloatText)


class VT1(ValueTraits):
    value_change_count = 0
    linked_trait = TF.Str()
    nested = TF.InstanceHP(klass=Nested).configure(TF.IHPMode.XL_N)
    a = TF.Str()
    b = TF.Int(0)
    c: Fixed[Self, ipw.Dropdown] = Fixed(ipw.Dropdown, created=lambda info: info["obj"].set_trait("options", [1, 2, 3]))
    change_owners = traitlets.Tuple()
    on_change_counts = TF.Int(0)

    value_traits_persist = NameTuple("a", "b")
    parent_dlink = NameTuple("linked_trait")

    @override
    def on_change(self, change: menubox.ChangeType):
        self.log.info(f"{self} value updated {change['new']}")
        self.on_change_counts += 1
        self.change_owners = (*self.change_owners, change["owner"])

    @traitlets.observe("value")
    def _observe_value(self, change):
        assert change["new"]() == change["old"](), "Should return same result"
        self.value_change_count += 1


class VT2(VT1):
    value_traits_persist = NameTuple("vt1")
    vt1 = traitlets.Instance(VT1, allow_none=True)
    update_counts = TF.Int(0)
    on_change_counts = TF.Int(0)

    @traitlets.default("vt1")
    def _defaualt_vt1(self):
        return VT1(parent=self)

    @traitlets.observe("value")
    def observe_update_count(self, change):
        self.log.info(f"{self} value updated {change['new']}")
        self.update_counts += 1

    @override
    def on_change(self, change: menubox.ChangeType):
        self.on_change_counts += 1


async def test_value_traits():
    vt1 = VT1()
    assert vt1.value() == {"a": "", "b": 0}  # defaults for non-InstantHP traits
    assert vt1.on_change_counts == 0
    assert vt1.value_change_count == 0  # No defaults
    vt1.a = "alone"
    assert vt1.on_change_counts == 1
    assert vt1.value_change_count == 1
    assert vt1.value() == {"a": "alone", "b": 0}

    # Check ignore change
    with vt1.ignore_change():
        vt1.a = "An ignored change"
    assert vt1.on_change_counts == 1, "'shouldn't have changed from above"
    assert vt1.value_change_count == 1, "'shouldn't have changed from above"
    assert vt1.a == "An ignored change"

    # Check value_traits: nested, adding, removing and None
    assert not vt1.trait_has_value("nested")
    vt1.add_value_traits("nested.number.value")
    assert (vt1, "nested") in vt1._vt_reg_value_traits
    assert len(vt1._vt_reg_value_traits) == 1
    assert len(vt1._vt_reg_value_traits_persist) == 2
    vt1.disable_ihp("nested")
    assert vt1.on_change_counts == 1
    assert vt1.value_change_count == 1
    vt1._reset_trait("nested")
    assert vt1.nested
    assert vt1.value_change_count == 2
    vt1.drop_value_traits("nested.number.value")
    assert vt1.on_change_counts == 2
    assert vt1.value_change_count == 2
    assert len(vt1._vt_reg_value_traits) == 0
    vt1.value = {"a": "change two at once", "b": 3}
    assert vt1.value() == {"a": "change two at once", "b": 3}  # type: ignore
    assert vt1.value_change_count == 3, "Should get called once per set of changes"
    assert vt1.on_change_counts == 4, "Called for each update"

    # Check
    vt2 = VT2()
    assert vt2.value() == {"vt1": {"a": "", "b": 0}}
    assert vt2.to_json() == '{\n  "vt1": {\n    "a": "",\n    "b": 0\n  }\n}'
    assert vt2.on_change_counts == 0

    vt2.value_traits_persist = ("vt1.value",)
    assert vt2.value() == {"vt1.value": {"a": "", "b": 0}}
    # assert vt2.update_counts == 2
    assert isinstance(vt2.vt1, VT1)
    vt2.vt1.a = "Some value"
    assert vt2.on_change_counts == 1, "a & it's value"
    assert vt2.value() == {"vt1.value": {"a": "Some value", "b": 0}}
    # assert vt2.update_counts == 3
    vt2.vt1.b = 332
    assert vt2.get_value("vt1.b") == 332, "Dotted name access"
    assert vt2.get_value("vt1.No_value") is None, "Returns default"
    assert vt2.on_change_counts == 2, "b & it's value"
    assert vt2.value() == {"vt1.value": {"a": "Some value", "b": 332}}

    vt2.linked_trait = "new value"
    assert vt2.vt1.linked_trait == "new value"

    vt22 = VT2(value=vt2.value, value_traits_persist=["vt1.value"])

    assert vt22.value() == vt2.value()

    # assert vt2.update_counts

    vt22.vt1 = VT1()
    assert vt22.vt1 is not vt2.vt1

    vt1.value_traits_persist = (*vt1.value_traits_persist, "nested.number")

    assert (vt1, "nested") in vt1._vt_reg_value_traits_persist, "the hash should match"
    assert (
        vt1.nested,
        "number",
    ) in vt1._vt_reg_value_traits_persist, "the hash should match"
    assert len(vt1._vt_reg_value_traits_persist) == 4, "Monitors for changes throughout"
    assert vt1.nested.number
    assert len(vt1._vt_reg_value_traits_persist) == 5, "Monitors for changes throughout"
    # Check swapping out a HasTraits instance updates the register
    numberwidget = vt1.nested.number
    assert (numberwidget, "value") in vt1._vt_reg_value_traits_persist
    vt1.nested.set_trait("number", ipw.FloatText(description="new number"))
    assert len(vt1._vt_reg_value_traits_persist) == 5, "Monitors for changes throughout"

    assert (numberwidget, "value") not in vt1._vt_reg_value_traits_persist
    assert (vt1.nested.number, "value") in vt1._vt_reg_value_traits_persist
    assert len(vt1._vt_reg_value_traits_persist) == 5, "Length shouldn't have changed"

    # Value observer
    key = (vt1.nested.number, "value")
    assert key in vt1._vt_reg_value_traits_persist, "Value observer is registered"
    vt1.nested.number.value = 2
    assert vt1.value() == {"a": "change two at once", "b": 3, "nested.number": 2.0}  # type: ignore

    with pytest.raises(TypeError):
        vt1.add_value_traits("not_a_trait")

    # Test updates register for nested
    nested_old = vt1.nested
    assert (nested_old, "number") in vt1._vt_reg_value_traits_persist
    nested = Nested()
    vt1.set_trait("nested", nested)
    assert (
        nested_old,
        "number",
    ) not in vt1._vt_reg_value_traits_persist, "should be deregisetered"
    assert (nested, "number") in vt1._vt_reg_value_traits_persist, "should be deregisetered"

    vt2.on_change_counts = 0
    # Check removing items
    vt2vt1 = vt2.vt1
    assert vt2.on_change_counts == 0
    vt2vt1.b = 2
    assert vt2.on_change_counts == 1

    vt2.set_trait("vt1", None)
    assert vt2.value() == {"vt1.value": None}
    assert vt2.on_change_counts == 2
    vt2vt1.b = 2
    assert vt2.on_change_counts == 2, "Should not have updated"

    vt1.close()

    vt2vt1 = vt2.vt1 = VT1(parent=vt2)
    vt2.close()
    assert vt2vt1.closed, "Should close when parent closes"


async def test_value_trait_load_bytes():
    import orjson

    v = VT1()
    val = orjson.dumps(v, menubox.pack.json_default)
    v2 = VT1(value=val)
    assert v.to_json() == v2.to_json()


async def test_vt1_fixed_widget():
    v = VT1(value_traits_persist=["c"])
    assert v.value() == {"c": None}
    v.load_value({"c": 1})
    assert v.value() == {"c": 1}
    assert v.c in v.change_owners


async def test_vt1_nested_fixed_widget():
    parent1 = VT1(name="parent 1")
    parent2 = VT1(name="parent 2")

    # Start with parent1
    v = VT1(parent=parent1, value_traits_persist=["parent.c"])
    assert v._vt_reg_value_traits_persist == {(v, "parent"), (parent1.c, "value")}
    assert v.value() == {"parent.c": None}
    v.load_value({"parent.c": 1})
    assert v.value() == {"parent.c": 1}
    assert parent1.c in v.change_owners

    # Remove the parent
    v.set_trait("parent", None)
    assert v._vt_reg_value_traits_persist == {(v, "parent")}
    assert v.value() == {"parent.c": None}

    # Set parent2 as the parent
    v.set_trait("parent", parent2)
    parent2.c.value = 3
    assert v._vt_reg_value_traits_persist == {(v, "parent"), (parent2.c, "value")}
