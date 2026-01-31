from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Self, override

import traitlets

from menubox import Menubox, TaskType, throttle, utils
from menubox.trait_factory import TF
from menubox.trait_types import ChangeType, NameTuple
from menubox.valuetraits import ValueTraits

if TYPE_CHECKING:
    from collections.abc import Generator

    from ipywidgets import Widget


class ChildrenSetter(ValueTraits):
    """
    Sets the `children` trait of the object `<self.parent>.<self.name>` dynamically when either the object
    changes or the state of a child changes. `parent.layout.visibility` is set to 'hidden' when there are no
    children and `visible` when it does.

    It is available as the InstanceHP hook 'set_children'.
    """

    SINGLE_BY = ("parent", "name")
    _AUTO_VALUE = False
    _prohibited_value_traits: ClassVar = set()
    _dottednames = NameTuple()

    children = traitlets.Callable()
    "The function that points to widgets relative to the parent to monitor such as `lambda p: p.box`."

    parent_dlink = NameTuple[Self](lambda p: (p.log,))

    @traitlets.observe("children")
    def _observe_children(self, change: ChangeType):
        if callable(c := change["new"]):
            try:
                self._dottednames = tuple(utils.dottedpath(c) if callable(c) else utils.iterflatten(c))
            except Exception as e:
                self.on_error(e, f"Failed to extract keys from {c!r}")
            self.update()

    def __repr__(self) -> str:
        return f"<ChildrenSetter at {id(self)} on {utils.fullname(self.parent)}.{self.name}>"

    def _make_traitnames(self) -> Generator[str, Any, None]:
        yield f"parent.{self.name}"
        for k in self._dottednames:
            yield from (f"parent.{k}.layout.visibility", f"parent.{k}.comm")

    @override
    def on_change(self, change: ChangeType) -> None:
        if (parent := self.parent) and not self.parent.closed and (pen := self.update()) and pen not in parent.tasks:
            parent.tasks.add(pen)
            pen.add_done_callback(parent.tasks.discard)

    @throttle(0.01, tasktype=TaskType.update_children)
    def update(self):
        if (parent := self.parent) and not self.parent.closed:
            if box := getattr(parent, self.name):
                children = tuple(parent.get_widgets(self.children))
                if children != box.children:
                    with box.hold_trait_notifications():
                        box.set_trait("children", children)
                        utils.set_visibility(box, bool(children))  # Hide/show the box based on if it has children
            self.set_trait("value_traits", self._make_traitnames())


class WidgetWatcher(ValueTraits):
    """
    Watches for visibility changes in the `widgets` dict calling `parent.mb_refresh` when a change is observed.

    Both `parent` and `widgets` should be set externally.
    """

    parent: TF.InstanceHP[Any, Menubox, Menubox] = TF.parent(Menubox)
    _AUTO_VALUE = False
    _prohibited_value_traits: ClassVar = set()
    widgets: TF.InstanceHP[Any, set[Widget], set[Widget]] = TF.Set()
    "A mapping of `widget.model_id`:`widget` that are to be watched."
    _widgets = TF.Dict()
    value_traits = NameTuple[Self](lambda p: (p.widgets,))

    def _make_traitnames(self) -> Generator[str, Any, None]:
        reg, current = self._widgets, set()
        yield "widgets"
        for widget in self.widgets:
            k = widget.model_id
            reg[k] = widget
            current.add(k)
            yield f"_widgets.{k}.layout.visibility"
            yield f"_widgets.{k}.comm"
        for k in current.difference(reg):
            reg.pop(k)

    @override
    def on_change(self, change: ChangeType) -> None:
        if (parent := self.parent) and not parent.closed:
            if (change["name"] == "widgets") and change["new"] != change["old"]:
                self.set_trait("value_traits", self._make_traitnames())
            elif parent.view_active and change["name"] == "visibility":
                parent.mb_refresh()
