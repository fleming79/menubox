from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, override

import traitlets

from menubox import ProposalType, TaskType, throttle, utils
from menubox.trait_types import ChangeType, NameTuple
from menubox.valuetraits import ValueTraits

if TYPE_CHECKING:
    from collections.abc import Generator


class ChildrenSetter(ValueTraits):
    """
    Sets the `children` trait of the object `<self.parent>.<self.name>` dynamically when either the object
    changes or the state of the children changes.
    """

    SINGLE_BY = ("parent", "name")
    _AUTO_VALUE = False
    _prohibited_value_traits: ClassVar = set()
    _dottednames = NameTuple()

    children = traitlets.Any()
    "Objects from the parent if they want to be watched."

    parent_dlink = NameTuple("log")
    value_traits = NameTuple("children")

    @traitlets.validate("children")
    def _validate_children(self, proposal: ProposalType):
        value = proposal["value"]
        self._dottednames = tuple(utils.extract_keys(value) if callable(value) else utils.iterflatten(value))
        return value

    def __repr__(self) -> str:
        return f"<ChildrenSetter at {id(self)} on {utils.fullname(self.parent)}.{self.name}>"

    def _make_traitnames(self) -> Generator[str, Any, None]:
        yield from ("children", f"parent.{self.name}")
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
