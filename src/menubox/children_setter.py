from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Self, override

import traitlets

from menubox import TaskType, throttle, utils
from menubox.trait_types import ChangeType, NameTuple
from menubox.valuetraits import ValueTraits

if TYPE_CHECKING:
    from collections.abc import Generator


class ChildrenSetter(ValueTraits):
    """
    Sets the `children` trait of the object `<self.parent>.<self.name>` dynamically when either the object
    changes or the state of a child changes.

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
                box.set_trait("children", parent.get_widgets(self.children))
            self.set_trait("value_traits", self._make_traitnames())
