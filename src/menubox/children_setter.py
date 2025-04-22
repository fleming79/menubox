from __future__ import annotations

from typing import override

from ipywidgets import Box
from traitlets import Tuple, Unicode

from menubox.mb_async import TaskType, debounce
from menubox.trait_types import ChangeType, NameTuple
from menubox.valuetraits import ValueTraits


class ChildrenSetter(ValueTraits):
    "Refreshes the children in an object belonging to dottednames in the parent as they change."

    SINGLE_BY = ("parent", "name")
    _AUTO_VALUE = False
    _prohibited_value_traits = set()  # noqa: RUF012
    dottednames = Tuple(read_only=True)
    nametuple_name = Unicode(help="The name in the parent of a tuple to obtain the dotted names")
    parent_dlink = NameTuple("log")
    value_traits = NameTuple("dottednames", "nametuple_name")

    @override
    def on_change(self, change: ChangeType):
        if change["owner"] is self.parent:
            if change["name"] == self.name and isinstance(change["old"], Box):
                change["old"].set_trait("children", ())
            elif change["name"] == self.nametuple_name:
                self._update_dotted_names_from_parent_nametuple()
        if change["owner"] is self:
            if change["name"] == "nametuple_name":
                self._update_dotted_names_from_parent_nametuple()
            if change["name"] == "dottednames":
                self.set_trait("value_traits", self._make_traitnames())
        self.update()

    def _update_dotted_names_from_parent_nametuple(self):
        if self.nametuple_name:
            dottednames = getattr(self.parent, self.nametuple_name)
            self.set_trait("dottednames", dottednames)

    def _make_traitnames(self):
        yield "dottednames"
        yield "nametuple_name"
        if self.nametuple_name:
            yield f"parent.{self.nametuple_name}"
        yield f"parent.{self.name}"
        for dotname in self.dottednames:
            yield f"parent.{dotname}"
            yield f"parent.{dotname}.layout.visibility"
            yield f"parent.{dotname}.comm"

    @debounce(0.01, tasktype=TaskType.update)
    def update(self):
        if self.parent and (box := getattr(self.parent, self.name)):
            box.set_trait("children", self.parent.get_widgets(self.dottednames, show=True))
