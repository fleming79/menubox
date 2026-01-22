from __future__ import annotations

from typing import ClassVar, override

from traitlets import Callable, Dict, Tuple, Unicode, observe

from menubox import debounce
from menubox.trait_types import ChangeType, NameTuple
from menubox.valuetraits import ValueTraits


class ChildrenSetter(ValueTraits):
    "Sets the children in an object belonging to dottednames in the parent as they change."

    SINGLE_BY = ("parent", "name")
    _AUTO_VALUE = False
    _prohibited_value_traits: ClassVar = set()
    dottednames = Tuple(read_only=True)
    nametuple_name = Unicode(help="The name in the parent of a tuple to obtain the dotted names")
    children = Callable(None, allow_none=True)
    "A callable that should return objects from the parent if they want to be watched."
    loaded_widgets = Dict()
    "A mapping to the the loaded_widgets. "
    parent_dlink = NameTuple("log")
    value_traits = NameTuple("dottednames", "nametuple_name", "children")

    @override
    def on_change(self, change: ChangeType):
        self.update()

    @observe("closed")
    def _child_setter_observe_closed(self, _):
        if self.children:
            self.loaded_widgets.clear()

    def _make_traitnames(self):
        yield from ("dottednames", "nametuple_name", "children", f"parent.{self.name}")
        for name in self.dottednames:
            yield f"parent.{name}"
        if self.nametuple_name:
            yield f"parent.{self.nametuple_name}"
            for name in getattr(self.parent, self.nametuple_name, ()):
                yield f"parent.{name}"
        for k in self.loaded_widgets:
            yield from (f"loaded_widgets.{k}.layout.visibility", f"loaded_widgets.{k}.comm")

    @debounce(0.01)
    async def update(self):
        # debounce used for thread safety
        if parent := self.parent:
            await parent
            widgets = {}
            dottednames = list(self.dottednames)
            if self.nametuple_name:
                dottednames.extend(getattr(parent, self.nametuple_name, ()))
            if box := getattr(self.parent, self.name):
                for widget in self.parent.get_widgets(self.children, dottednames):
                    k = f"model_id_{widget.model_id}"
                    widgets[k] = widget
                box.set_trait("children", tuple(widgets.values()))
            self.loaded_widgets = widgets
            self.set_trait("value_traits", self._make_traitnames())
