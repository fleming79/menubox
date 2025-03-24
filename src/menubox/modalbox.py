from __future__ import annotations

from typing import TYPE_CHECKING, Self, override

import ipywidgets as ipw
import traitlets

from menubox import mb_async, utils
from menubox import trait_factory as tf
from menubox.css import CSScls
from menubox.hasparent import HasParent, Parent
from menubox.log import log_exceptions
from menubox.trait_types import ChangeType, StrTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

__all__ = ["Modalbox"]

# TODO: make generic for parent
class Modalbox(HasParent, ipw.VBox):
    parent = Parent(HasParent)
    obj = traitlets.Any(read_only=True)
    button_expand = tf.Button_modal()
    button_collapse = tf.Button_modal(disabled=True)
    box = tf.Box().configure(allow_none=True, load_default=False).hooks(set_parent=False)
    header_children = StrTuple("H_FILL")
    expanded = traitlets.Bool(False, read_only=True)
    html_title = tf.HTML_Title().configure(allow_none=True, load_default=False)
    header = tf.HBox().configure(allow_none=True).hooks(add_css_class=CSScls.ModalboxHeader)
    _box_children = traitlets.Tuple()

    @log_exceptions
    def __init__(
        self,
        *,
        obj: ipw.Widget | Callable | tuple | str,
        title: str,
        parent: HasParent | None = None,
        expand=False,
        box: ipw.Box | str | None = None,
        title_tooltip="",
        button_expand_description="",
        button_expand_tooltip="Expand",
        button_collapse_description="🗕",
        button_collapse_tooltip="Collapse",
        header_children: Iterable[str] = (),
        on_expand: Callable[[Self], None] | str | None = None,
        on_collapse: Callable[[Self], None] | str | None = None,
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
        if self.parent:
            self.log = self.parent.log
        if not callable(obj) and not isinstance(obj, ipw.Widget | tuple | str):
            msg = f"view should be an instance of 'Box' or callable or tuple that returns a 'Box' not '{type(obj)}'"
            raise TypeError(msg)
        if isinstance(box, str):
            box = utils.getattr_nested(parent, box)
        if isinstance(on_expand, str):
            on_expand = utils.getattr_nested(parent, on_expand)
        if isinstance(on_collapse, str):
            on_collapse = utils.getattr_nested(parent, on_collapse)
        self.set_trait("obj", obj)
        if box:
            self.set_trait("box", box)
        fstr = parent.fstr if parent else utils.fstr
        title = fstr(title)
        if title:
            self.instanceHP_enable_disable(
                "html_title", {"description": f"<b>{title}</b>", "tooltip": fstr(title_tooltip)}
            )
        if header_children:
            self.header_children = header_children
        self.instanceHP_enable_disable(
            "button_expand",
            {"description": fstr(button_expand_description or title), "tooltip": fstr(button_expand_tooltip)},
        )
        self.instanceHP_enable_disable(
            "button_collapse",
            {"description": fstr(button_collapse_description), "tooltip": fstr(button_collapse_tooltip)},
        )
        super().__init__(parent=parent, children=(self.button_expand,), **kwargs)
        if orientation == "horizontal":
            self.layout.flex_flow = "row"
            if self.header:
                self.header.layout.margin = ""
        self._on_expand = on_expand
        self._on_collapse = on_collapse
        if expand:
            mb_async.call_later(0.1, self.expand)

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
        # open is already used
        self.button_collapse.disabled = False
        get_widgets = self.parent.get_widgets if self.parent else self._get_widgets
        if self.header:
            self.header.children = tuple(get_widgets(self.button_collapse, self.html_title, self.header_children))
            if self.layout.flex_flow != "row":
                self.header.layout.border_bottom = self.box.layout.border_top if self.box else self.layout.border_top

        children = tuple(get_widgets(self.header or self.button_collapse, self.obj))
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
        return tuple(w for w in utils.iterflatten(items) if isinstance(w, ipw.Widget))

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
                self._on_expand(self)
        else:
            self.remove_class(CSScls.Modalbox)
            if callable(self._on_collapse):
                self.log.debug(f"_on_collapse call: {self._on_expand}")
                self._on_collapse(self)
