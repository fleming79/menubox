from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Self, override

import traitlets

from menubox import Menubox, TaskType, debounce, utils
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
    autohide = TF.Bool(True)
    "Hides the box when there are not children and vice versa."
    set_showbox = TF.Bool(False)
    "Enable 'showbox' functionality on widgets. 'children' must point to a tuple on the parent to synchronise."

    children = traitlets.Any()
    "The function that points to widgets relative to the parent to monitor such as `lambda p: p.box`."

    parent_dlink = NameTuple[Self](lambda p: (p.log,))
    value_traits = NameTuple[Self](lambda p: (p.parent, p.children))

    def __repr__(self) -> str:
        return f"<ChildrenSetter at {id(self)} on {utils.fullname(self.parent)}.{self.name}>"

    def _make_traitnames(self) -> Generator[str, Any, None]:
        yield from (f"parent.{self.name}", "children")
        if self.set_showbox:
            yield f"parent.{self.name}.children"
        for k in self._dottednames:
            yield from (f"parent.{k}.layout.visibility", f"parent.{k}.comm")

    @override
    def on_change(self, change: ChangeType) -> None:
        if (parent := self.parent) and not self.parent.closed:
            if change["name"] == "children":
                if change["owner"] is self:
                    if callable(c := change["new"]):
                        try:
                            self._dottednames = tuple(utils.dottedpath(c) if callable(c) else utils.iterflatten(c))
                        except Exception as e:
                            self.on_error(e, f"Failed to extract keys from {c!r}")
                        if self.set_showbox:
                            assert len(self._dottednames) == 1
                        self._update()
                elif self.set_showbox and change["owner"] is getattr(parent, self.name):
                    utils.setattr_nested(parent, self._dottednames[0], change["new"])
                    for c in set(change["old"]).difference(change["new"]):
                        if isinstance(c, Menubox):
                            c.showbox = None
            elif self.trait_has_value("children") and (pen := self.update()) and pen not in parent.tasks:
                parent.tasks.add(pen)
                pen.add_done_callback(parent.tasks.discard)

    def _update(self):
        if (parent := self.parent) and not self.parent.closed:
            if box := getattr(parent, self.name):
                children = tuple(parent.get_widgets(self.children))
                if children != box.children:
                    box.set_trait("children", children)
                if self.autohide:
                    utils.set_visibility(box, bool(children))  # Hide/show the box based on if it has children
                if self.set_showbox:
                    for c in children:
                        if isinstance(c, Menubox):
                            c.showbox = box
            self.set_trait("value_traits", self._make_traitnames())

    @debounce(0.01, tasktype=TaskType.update_children)
    def update(self):
        self._update()


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
