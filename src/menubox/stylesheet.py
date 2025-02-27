from __future__ import annotations

import enum
import os
from typing import TYPE_CHECKING, override

from ipylab import to_selector
from ipylab.css_stylesheet import CSSStyleSheet

if TYPE_CHECKING:
    from asyncio import Task
    from collections.abc import Hashable

    from ipywidgets import DOMWidget


class CSSvar(enum.StrEnum):
    "CSS variables names intended to be used with MenuboxStylesheet"

    button_main_color = "button-main-color"
    button_menu_color = "button-menu-color"
    button_open_color = "button-open-color"
    button_modal_color = "button-modal-color"
    button_warning_color = "button-warning-color"
    button_dangerous_color = "button-dangerous-color"
    button_toggle_color = "button-toggle-color"
    button_shuffle_color = "button-shuffle-color"

    button_busy_border = "button-busy-border"
    button_active_view_border = "button-busy-border"

    menubox_vt_border = "MenuBoxVT-border"


class CSScls(enum.StrEnum):
    "CSS class names to use with MenuboxStylesheet"

    resize_both = "resize-both"
    resize_horizontal = "resize-horizontal"
    resize_vertical = "resize-vertical"

    tab_button = "tab-button"

    MenuBox = "Menubox"
    MenuBoxHeader = "Menubox-header"
    MenuBoxCenter = "Menubox-center"
    MenuBoxMenu = "Menubox-menu"
    MenuBoxShuffle = "Menubox-shuffle"

    MenuBoxVT = "MenuboxVT"

    ModalBoxHeader = "ModalBox-header"

    button = "button"
    button_modal = "button-modal"
    button_main = "button-main"
    button_menu = "button-menu"
    button_open = "button-open"
    button_warning = "button-warning"
    button_dangerous = "button-dangerous"
    button_toggle = "button-toggle"
    button_shuffle = "button-shuffle"

    button_is_busy = "button-busy"
    button_active_view = "button-active_view"

    async_run_button = "async_run_button"

    # stylesheet.set_variables({
    #     CSSvar.button_main_color: "var(--jp-brand-color1)",
    #     # CSSvar.button_menu_color: "var(--jp-brand-color1)",
    #     CSSvar.button_open_color: "Ivory",
    #     CSSvar.button_modal_color: "LightGoldenrodYellow",
    #     CSSvar.button_warning_color: "Orange",
    #     CSSvar.button_dangerous_color: "OrangeRed",
    #     CSSvar.button_toggle_color: "Gainsboro",
    #     CSSvar.button_shuffle_color: "Bisque",
    #     CSSvar.button_busy_border: " solid 1px LightGrey",
    #     CSSvar.button_active_view_border: " solid 1px LightGrey",
    # })


class MenuboxStylesheet(CSSStyleSheet):
    PRIMARY_PREFIX = "menubox"
    _prefix = ""
    _prefix_marker = "✂️"
    _init_task: Task | None = None
    TEMPLATE = f"""
:root {{
--✂️{CSSvar.button_main_color}: var(--jp-brand-color1);
--✂️{CSSvar.button_menu_color}: var(--jp-brand-color1);
--✂️{CSSvar.button_open_color}: "Ivory";
--✂️{CSSvar.button_modal_color}: "LightGoldenrodYellow";
--✂️{CSSvar.button_warning_color}: "Orange";
--✂️{CSSvar.button_dangerous_color}: "OrangeRed";
--✂️{CSSvar.button_toggle_color}: "Gainsboro";
--✂️{CSSvar.button_shuffle_color}: "Bisque";
--✂️{CSSvar.button_busy_border}: " solid 1px LightGrey";
--✂️{CSSvar.button_active_view_border}: " solid 1px LightGrey";
--✂️{CSSvar.menubox_vt_border}: " solid 1px LightGrey";

}}

.✂️{CSScls.resize_both} {{ resize: both;}}
.✂️{CSScls.resize_horizontal} {{ resize: horizontal;}}
.✂️{CSScls.resize_vertical} {{ resize: vertical;}}

.✂️{CSScls.button} {{width: max-content; flex: 0 0 auto;}}
.✂️{CSScls.button_main} {{ background-color: var(--✂️{CSSvar.button_main_color});}}
.✂️{CSScls.button_menu} {{ background-color: var(--✂️{CSSvar.button_menu_color});}}
.✂️{CSScls.button_open} {{ background-color: var(--✂️{CSSvar.button_open_color});}}
.✂️{CSScls.button_modal} {{ background-color: var(--✂️{CSSvar.button_modal_color});}}
.✂️{CSScls.button_warning} {{ background-color: var(--✂️{CSSvar.button_warning_color});}}
.✂️{CSScls.button_dangerous} {{ background-color: var(--✂️{CSSvar.button_dangerous_color});}}
.✂️{CSScls.button_toggle} {{ background-color: var(--✂️{CSSvar.button_toggle_color});}}
.✂️{CSScls.button_shuffle} {{ background-color: var(--✂️{CSSvar.button_shuffle_color});}}

.✂️{CSScls.button_is_busy} {{ border: var(✂️{CSSvar.button_busy_border});}}
.✂️{CSScls.button_active_view} {{ border: var(✂️{CSSvar.button_active_view_border});}}

/* Boxes */
.✂️{CSScls.MenuBox} {{}}
.✂️{CSScls.MenuBoxHeader} {{
    flex: 0 0 auto;
    flex_flow: row wrap;
    "height": "max-content";}}
.✂️{CSScls.MenuBoxMenu} {{
    flex: 0 0 auto;
    flex_flow: row wrap;
    "height": "max-content";}}
.✂️{CSScls.MenuBoxShuffle} {{
    flex: 0 0 auto;
    flex_flow: row wrap;
    "height": "max-content";}}
.✂️{CSScls.MenuBoxVT} {{
    "border": "solid 1px LightGrey"}}
    """

    @classmethod
    @override
    def _single_key(cls, kwgs: dict) -> Hashable:
        return cls.PRIMARY_PREFIX

    async def _restore(self, _):
        if not self._init_task:
            self._init_task = self.replace(self.default_stylesheet)
        super()._restore(_)

    async def ready(self):
        await super().ready()
        if self._init_task:
            await self._init_task

    @property
    def prefix(self):
        if not self._prefix:
            self._prefix = to_selector(os.getpid(), prefix=self.PRIMARY_PREFIX).strip(".") + "-"
        return self._prefix

    @property
    def default_stylesheet(self):
        return self.TEMPLATE.replace(self._prefix_marker, self._prefix)

    def add_class(self, widget: DOMWidget, *name: str | CSScls):
        """Adds one or more CSS classes to a DOMWidget.

        The class names are requiried to be defined in this stylesheet.

        If a class is already present, it is not added again.

        Args:
            widget: The DOMWidget to add the class(es) to.
            *name: One or more CSS class names or CSScls objects to add.
        """
        prefix = self.prefix
        extra = (n_ for n in name if (n_ := prefix + n) not in widget._dom_classes)
        widget._dom_classes = (*widget._dom_classes, *extra)

    def remove_class(self, widget: DOMWidget, *name: str | CSScls):
        """Removes CSS classes from a DOMWidget.

        The class names are requiried to be defined in this stylesheet.

        Args:
            widget: The DOMWidget to remove the classes from.
            *name: The CSS class names (with or without prefix) or CSScls objects to remove.
        """
        prefix = self.prefix
        widget._dom_classes = tuple(n_ for n in name if (n_ := prefix + n) not in widget._dom_classes)

    @override
    def set_variables(self, variables: dict[str, str]) -> Task[dict[str, str]]:
        """Sets CSS variables for the stylesheet or current page.

        This method takes a dictionary of CSS variable names and values, prefixes
        the variable names with the stylesheet's prefix (if they don't already have
        a prefix), and then calls the superclass's `set_variables` method to actually
        set the variables.

        Args:
            variables (dict[str, str]): A dictionary where the keys are CSS variable names
            (e.g., 'color', '--primary-color') and the values are the corresponding CSS values
            (e.g., 'red', '#FF0000').
        Returns:
            Task[dict[str, str]]: A Task that resolves to the dictionary of CSS variables that were set.
        """
        variables_ = {}
        prefix = "--" + self.prefix
        for key, val in variables.items():
            key_ = key if key.startswith("--") else prefix + key
            variables_[key_] = val
        return super().set_variables(variables)
