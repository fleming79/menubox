"""A collection of InstanceHP factories.

Factory items include:
* Popular widgets
* Imported widgets to avoid circular imports
* Factories with custom default
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

import ipylab
import ipywidgets as ipw

import menubox.async_run_button
import menubox.widgets
from menubox import mb_async
from menubox.css import CSScls
from menubox.defaults import NO_VALUE
from menubox.instance import IHPCreate, IHPDlinkType, InstanceHP
from menubox.instance import IHPDlinkType as DLink
from menubox.instance import instanceHP_wrapper as ihpwrap

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "AsyncRunButton",
    "AsyncRunButton_update",
    "MenuboxHeader",
    "MenuboxCenter",
    "MenuboxMenu",
    "MenuboxShuffle",
    "Box",
    "Button_main",
    "Button_dangerous",
    "Button_menu",
    "Button_modal",
    "Button_open",
    "Button_shuffle",
    "Button_toggle",
    "Button_cancel",
    "CodeEditor",
    "CodeEditorValidate",
    "Combobox",
    "ComboboxValidate",
    "Dropdown",
    "DLink",
    "FileUpload",
    "FloatTextValidate",
    "HBox",
    "HTML",
    "HTML_Title",
    "IHPCreate",
    "IHPDlinkType",
    "InstanceHP",
    "IntTextValidate",
    "Label",
    "Select",
    "SelectMultipleValidate",
    "Menubox",
    "Modalbox",
    "Repositories",
    "SelectRepository",
    "Task",
    "Text",
    "TextValidate",
    "TextareaValidate",
    "VBox",
    "MarkdownViewer",
]

if TYPE_CHECKING:
    import menubox.menubox
    import menubox.modalbox
    import menubox.repository
    import menubox.widgets


# Ipywidgets shortcuts
Box = ihpwrap(ipw.Box)
VBox = ihpwrap(ipw.VBox)
HBox = ihpwrap(ipw.HBox)

HTML = ihpwrap(ipw.HTML)
Dropdown = ihpwrap(ipw.Dropdown)
Combobox = ihpwrap(ipw.Combobox)
Select = ihpwrap(ipw.Select)
Text = ihpwrap(ipw.Text)
Label = ihpwrap(ipw.Label)
SelectionSlider = ihpwrap(ipw.SelectionSlider, defaults={"options": (NO_VALUE,)})


# Button
Button_main = ihpwrap(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_main))
Button_open = ihpwrap(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_open))
Button_cancel = ihpwrap(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_cancel))
Button_dangerous = ihpwrap(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_dangerous))
Button_modal = ihpwrap(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_modal))
Button_menu = ihpwrap(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_menu))
Button_toggle = ihpwrap(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_toggle))
Button_shuffle = ihpwrap(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_shuffle))
FileUpload = ihpwrap(ipw.FileUpload, add_css_class=(CSScls.button, CSScls.button_type_main))

MenuboxHeader = ihpwrap(
    ipw.HBox,
    dlink={"source": ("self", "border"), "target": "layout.border_bottom"},
    add_css_class=(CSScls.Menubox_item, CSScls.header),
)
MenuboxCenter = ihpwrap(ipw.VBox, add_css_class=(CSScls.Menubox_item, CSScls.centerbox))
MenuboxMenu = ihpwrap(ipw.HBox, add_css_class=(CSScls.Menubox_item, CSScls.menu))
MenuboxShuffle = ihpwrap(ipw.HBox, add_css_class=(CSScls.Menubox_item, CSScls.shuffle))


# Ipywidget String
HTML_Title = ihpwrap(
    ipw.HTML,
    defaults={
        "layout": {
            "width": "max-content",
            "padding": "0px 10px 0px 15px",
            "flex": "0 0 auto",
        },
        "style": {"description_width": "initial"},
        "description_allow_html": True,
    },
)


CodeEditor = ihpwrap(ipylab.CodeEditor)

TextareaValidate = ihpwrap(menubox.widgets.TextareaValidate, defaults={"value": ""})
ComboboxValidate = ihpwrap(menubox.widgets.ComboboxValidate, defaults={"value": ""})
TextValidate = ihpwrap(menubox.widgets.TextValidate, defaults={"value": ""})
FloatTextValidate = ihpwrap(menubox.widgets.FloatTextValidate, defaults={"value": 0})
IntTextValidate = ihpwrap(menubox.widgets.IntTextValidate, defaults={"value": 0})
SelectMultipleValidate = ihpwrap(menubox.widgets.SelectMultipleValidate, defaults={"value": ()})
CodeEditorValidate = ihpwrap(menubox.widgets.CodeEditorValidate, defaults={"value": ""})
MarkdownViewer = ihpwrap(menubox.widgets.MarkdownViewer)

# menubox

Menubox = ihpwrap(cast(type["menubox.menubox.Menubox"], "menubox.menubox.Menubox"))
MenuboxVT = ihpwrap(cast(type["menubox.menuboxvt.MenuboxVT"], "menubox.menubox.MenuboxVT"))

AsyncRunButton = ihpwrap(
    cast(type["menubox.async_run_button.AsyncRunButton"], "menubox.async_run_button.AsyncRunButton"),
    defaults={"tasktype": mb_async.TaskType.general},
    add_css_class=CSScls.button_type_main,
)
AsyncRunButton_update = ihpwrap(
    cast(type["menubox.async_run_button.AsyncRunButton"], "menubox.async_run_button.AsyncRunButton"),
    defaults={"tasktype": mb_async.TaskType.update},
    add_css_class=CSScls.button_type_main,
)
Modalbox = ihpwrap(cast(type["menubox.modalbox.Modalbox"], "menubox.modalbox.Modalbox"))

Repository = ihpwrap(
    cast(type["menubox.repository.Repository"], "menubox.repository.Repository"),
    create=lambda config: config["parent"].home.repository,  # type: ignore
    on_replace_close=False,
    set_parent=False,
    read_only=False,
)
Repositories = ihpwrap(
    cast(type["menubox.repository.Repositories"], "menubox.repository.Repositories"),
    set_parent=False,
    dynamic_kwgs={"home": "home"},
    on_replace_close=False,
)
SelectRepository = ihpwrap(cast(type["menubox.repository.SelectRepository"], "menubox.repository.SelectRepository"))

# other
Task: Callable[..., InstanceHP[asyncio.Task | None]] = ihpwrap(asyncio.Task, allow_none=True, load_default=False)
