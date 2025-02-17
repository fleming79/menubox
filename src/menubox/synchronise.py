from __future__ import annotations

from ipywidgets import Box
from traitlets import Tuple

from menubox.trait_types import ChangeType, NameTuple
from menubox.valuetraits import ValueTraits


class ChildrenSetter(ValueTraits):
    "Refreshes the children in an object belonging to items in the parent as they change."

    SINGLETON_BY = ("parent", "name")
    _AUTO_VALUE = False
    _STRICT_VALUE = False
    _prohibited_value_traits = set()  # noqa: RUF012
    items = Tuple(read_only=True)
    parent_dlink = NameTuple("log")
    value_traits = NameTuple("items")
    _updating = False

    def on_change(self, change: ChangeType):
        if change["owner"] is self.parent and change["name"] == self.name and isinstance(change["old"], Box):
            change["old"].children = ()
        if change["owner"] is self and change["name"] == "items":
            self.set_trait("value_traits", self._make_traitnames())
        self.update()

    def _make_traitnames(self):
        yield "items"
        yield f"parent.{self.name}"
        for dotname in self.items:
            yield f"parent.{dotname}"
            yield f"parent.{dotname}.layout.visibility"

    def update(self):
        parent = self.parent
        if parent and not self._updating:
            self._updating = True
            try:
                box = getattr(parent, self.name)
                if box:
                    box.children = () if parent.closed else parent.get_widgets(self.items, show=True)
            finally:
                self._updating = False
