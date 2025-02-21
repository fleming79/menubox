from __future__ import annotations

from typing import override

from ipywidgets import Box
from traitlets import Tuple

from menubox.mb_async import TaskType, debounce
from menubox.trait_types import ChangeType, NameTuple
from menubox.valuetraits import ValueTraits


class ChildrenSetter(ValueTraits):
    "Refreshes the children in an object belonging to dottednames in the parent as they change."

    SINGLETON_BY = ("parent", "name")
    _AUTO_VALUE = False
    _prohibited_value_traits = set()  # noqa: RUF012
    dottednames = Tuple(read_only=True)
    parent_dlink = NameTuple("log")
    value_traits = NameTuple("dottednames")

    @override
    def on_change(self, change: ChangeType):
        if change["name"] == self.name and change["owner"] is self.parent and isinstance(change["old"], Box):
            change["old"].children = ()
        if change["owner"] is self and change["name"] == "dottednames":
            self.set_trait("value_traits", self._make_traitnames())
        self.update()

    def _make_traitnames(self):
        yield "dottednames"
        yield f"parent.{self.name}"
        for dotname in self.dottednames:
            yield f"parent.{dotname}"
            yield f"parent.{dotname}.layout.visibility"
            yield f"parent.{dotname}.comm"

    @debounce(0.01, tasktype=TaskType.update)
    def update(self):
        if self.parent and (box := getattr(self.parent, self.name)):
            box.children = self.parent.get_widgets(self.dottednames, show=True)
