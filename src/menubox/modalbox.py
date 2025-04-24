from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Self, override

import ipywidgets as ipw
import traitlets

from menubox import mb_async, utils
from menubox import trait_factory as tf
from menubox.css import CSScls
from menubox.hasparent import HasParent
from menubox.log import log_exceptions
from menubox.trait_types import ChangeType, S, StrTuple

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Modalbox"]


class Modalbox(HasParent, ipw.VBox, Generic[S]):
    obj = traitlets.Callable(read_only=True)
    button_expand = tf.Button_modal()
    button_collapse = tf.Button_modal(disabled=True)
    expanded = traitlets.Bool(False, read_only=True)
    html_title = tf.HTML_Title()
    header = tf.HBox().configure(allow_none=True, read_only=True).hooks(add_css_class=CSScls.ModalboxHeader)
    _box_children = traitlets.Tuple()
    parent_dlink = StrTuple("log")
    if TYPE_CHECKING:
        parent: tf.InstanceHP[Self, S, S]

    @log_exceptions
    def __init__(
        self,
        *,
        parent: S,
        obj: Callable[[S], utils.GetWidgetsInputType],
        title: str,
        expand=False,
        box: Callable[[S], ipw.Box] | None = None,
        title_tooltip="",
        button_expand_description="",
        button_expand_tooltip="Expand",
        button_collapse_description="🗕",
        button_collapse_tooltip="Collapse",
        header_children: Callable[[S], utils.GetWidgetsInputType] = lambda _: "H_FILL",
        on_expand: Callable[[S], Any] = lambda _: None,
        on_collapse: Callable[[S], Any] = lambda _: None,
        orientation="vertical",
        **kwargs,
    ) -> None:
        """
        obj:

        parent :
            The object that owns the Modalbox.

        if button_expand_description is not set, the description will be the
        same as title.

        expand: bool
            Expand on loading.

        box:
            The box where expanded content will appear.
            Note: the box contents will be overwritten/purged on expand and collapse.

        header_children:
            Dotted name access to attributes relative to parent.

        orientation: [vertical | horizontal]

        title & title_tooltip:
            Used in the HTML title. By default there is not HTML title.
        """
        if self._HasParent_init_complete:
            return
        self.set_trait("obj", obj)
        self._box_getter = box
        fstr = parent.fstr if isinstance(parent, HasParent) else utils.fstr
        title = fstr(title)
        if title:
            self.html_title.description = fstr("<b>{title}</b>")
            self.html_title.tooltip = fstr(title_tooltip)
        self.header_children = header_children
        self.button_expand.description = fstr(button_expand_description or title)
        self.button_expand.tooltip = fstr(button_expand_tooltip)
        self.button_collapse.description = fstr(button_collapse_description)
        self.button_collapse.tooltip = fstr(button_collapse_tooltip)

        super().__init__(parent=parent, children=(self.button_expand,), **kwargs)
        if orientation == "horizontal":
            self.layout.flex_flow = "row"
            if self.header:
                self.header.layout.margin = ""
        self._on_expand = on_expand
        self._on_collapse = on_collapse
        if expand:
            mb_async.call_later(0.1, self.expand)

    @property
    def box(self) -> ipw.Box | None:
        if self._box_getter:
            return self._box_getter(self.parent)
        return None

    @override
    async def button_clicked(self, b: ipw.Button):
        match b:
            case self.button_collapse:
                self.collapse()
            case self.button_expand:
                self.expand()

    @log_exceptions
    def expand(self):
        """Show the widget"""
        self.button_collapse.disabled = False
        if self.header:
            self.header.children = tuple(self._get_widgets(self.button_collapse, self.html_title, self.header_children))
            if self.layout.flex_flow != "row":
                self.header.layout.border_bottom = self.box.layout.border_top if self.box else self.layout.border_top
        children = tuple(self._get_widgets(self.header or self.button_collapse, self.obj))
        self.button_expand.disabled = True
        self.set_trait("expanded", True)
        if self.box:
            self.box.children = children
        else:
            self.children = children

    @mb_async.debounce(0.1)
    def refresh(self):
        """Reload widgets for the current state."""
        if self.expanded:
            self.expand()
        else:
            self.collapse()

    def _get_widgets(self, *items):
        return utils.get_widgets(*items, parent=self.parent if isinstance(self.parent, HasParent) else None)

    @log_exceptions
    def collapse(self):
        self.button_expand.disabled = False
        if self.box:
            self.box.children = ()
        self.children = (self.button_expand,)
        self.set_trait("expanded", False)

    @traitlets.observe("expanded")
    @log_exceptions
    def _observe_expanded(self, _: ChangeType):
        if self.expanded:
            self.add_class(CSScls.Modalbox)
            if callable(self._on_expand):
                self.log.debug(f"on_expand call: {self._on_expand}")
                self._on_expand(self.parent)  # type: ignore
        else:
            self.remove_class(CSScls.Modalbox)
            if callable(self._on_collapse):
                self.log.debug(f"_on_collapse call: {self._on_expand}")
                self._on_collapse(self.parent)  # type: ignore
