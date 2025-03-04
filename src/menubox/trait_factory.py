"""
Trait factory functions here simplify and unify adding traits to HasParent subclasses.

Each function creates an InstanceHP trait, similar to  traitlets.Instance,
but with special handling and features. By default subclasses of HasParent
will set the parent, enabling auto setting of Home, and other life cycle control.
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
from menubox.instance import instanceHP_wrapper as IHP

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "AsyncRunButton",
    "AsyncRunButton_update",
    "Accordion",
    "Audio",
    "BoundedFloatText",
    "BoundedIntText",
    "Box",
    "MenuboxHeader",
    "MenuboxCenter",
    "MenuboxMenu",
    "MenuboxShuffle",
    "Button_main",
    "Button_dangerous",
    "Button_menu",
    "Button_modal",
    "Button_open",
    "Button_shuffle",
    "Button_toggle",
    "Button_cancel",
    "Checkbox",
    "ColorPicker",
    "ColorsInput",
    "Combobox",
    "ComboboxValidate",
    "CoreWidget",
    "DLink",
    "DatePicker",
    "DatetimePicker",
    "Dropdown",
    "Dropdown",
    "FileUpload",
    "FloatProgress",
    "FloatRangeSlider",
    "FloatSlider",
    "FloatText",
    "FloatTextValidate",
    "FloatLogSlider",
    "FloatsInput",
    "GridBox",
    "HBox",
    "HTML",
    "HTMLMath",
    "HTML_Title",
    "IHP",
    "IHPCreate",
    "IHPDlinkType",
    "Image",
    "InstanceHP",
    "IntProgress",
    "IntRangeSlider",
    "IntSlider",
    "IntText",
    "IntTextValidate",
    "SelectMultipleValidate",
    "Label",
    "Menubox",
    "Modalbox",
    "NaiveDatetimePicker",
    "Output",
    "Password",
    "Play",
    "RadioButtons",
    "Repositories",
    "Select",
    "SelectMultiple",
    "SelectRepository",
    "SelectionRangeSlider",
    "SelectionSlider",
    "Stack",
    "Tab",
    "TagsInput",
    "Task",
    "Text",
    "TextValidate",
    "Textarea",
    "TextareaValidate",
    "TimePicker",
    "ToggleButton",
    "ToggleButtons",
    "VBox",
    "Valid",
    "ValueWidget",
    "MarkdownViewer",
    "CodeEditor",
    "SimpleOutput",
]

if TYPE_CHECKING:
    import menubox.menubox
    import menubox.modalbox
    import menubox.repository
    import menubox.widgets

# Ipywidget Core widget - may be useful.
CoreWidget = IHP(ipw.CoreWidget)
ValueWidget = IHP(ipw.ValueWidget)

# Ipywidget Bool
Checkbox = IHP(ipw.Checkbox)
ToggleButton = IHP(ipw.ToggleButton, add_css_class=(CSScls.button, CSScls.button_type_toggle))
Valid = IHP(ipw.Valid)

# Ipywidget Button
Button_main = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_main))
Button_open = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_open))
Button_cancel = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_cancel))
Button_dangerous = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_dangerous))
Button_modal = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_modal))
Button_menu = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_menu))
Button_toggle = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_toggle))
Button_shuffle = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_type_shuffle))

# Ipywidget Box
Box = IHP(ipw.Box)
VBox = IHP(ipw.VBox)
HBox = IHP(ipw.HBox)
GridBox = IHP(ipw.GridBox)

MenuboxHeader = IHP(
    ipw.HBox,
    dlink={"source": ("self", "border"), "target": "layout.border_bottom"},
    add_css_class=(CSScls.Menubox_item, CSScls.header),
)
MenuboxCenter = IHP(ipw.VBox, add_css_class=(CSScls.Menubox_item, CSScls.centerbox))
MenuboxMenu = IHP(ipw.HBox, add_css_class=(CSScls.Menubox_item, CSScls.menu))
MenuboxShuffle = IHP(ipw.HBox, add_css_class=(CSScls.Menubox_item, CSScls.shuffle))


# Ipywidget Float
FloatText = IHP(ipw.FloatText)
BoundedFloatText = IHP(ipw.BoundedFloatText)
FloatSlider = IHP(ipw.FloatSlider)
FloatProgress = IHP(ipw.FloatProgress)
FloatRangeSlider = IHP(ipw.FloatRangeSlider)
FloatLogSlider = IHP(ipw.FloatLogSlider)

# Ipywidget Int
IntText = IHP(ipw.IntText)
BoundedIntText = IHP(ipw.BoundedIntText)
IntSlider = IHP(ipw.IntSlider)
IntProgress = IHP(ipw.IntProgress)
IntRangeSlider = IHP(ipw.IntRangeSlider)
Play = IHP(ipw.Play)

# Ipywidget Color
ColorPicker = IHP(ipw.ColorPicker)

# Ipywidget Date
DatePicker = IHP(ipw.DatePicker)

# Ipywidget Datetime
DatetimePicker = IHP(ipw.DatetimePicker)
NaiveDatetimePicker = IHP(ipw.NaiveDatetimePicker)

# Ipywidget Time
TimePicker = IHP(ipw.TimePicker)

# Ipywidget Output
Output = IHP(ipw.Output, defaults={"layout": {"overflow": "auto"}})

# Ipywidget Selection
RadioButtons = IHP(ipw.RadioButtons)
ToggleButtons = IHP(ipw.ToggleButtons)
Dropdown = IHP(ipw.Dropdown)
Select = IHP(ipw.Select)
SelectionSlider = IHP(ipw.SelectionSlider, defaults={"options": (NO_VALUE,)})
SelectMultiple = IHP(ipw.SelectMultiple)
SelectionRangeSlider = IHP(ipw.SelectionRangeSlider)
SelectMultiple = IHP(ipw.SelectMultiple)
Dropdown = IHP(ipw.Dropdown)

# Ipywidget Selection container
Tab = IHP(ipw.Tab)
Accordion = IHP(ipw.Accordion)
Stack = IHP(ipw.Stack)

# Ipywidget String
HTML = IHP(ipw.HTML)
HTML_Title = IHP(
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

HTMLMath = IHP(ipw.HTMLMath)
Label = IHP(ipw.Label)
Text = IHP(ipw.Text)
Textarea = IHP(ipw.Textarea)
Password = IHP(ipw.Password)
Combobox = IHP(ipw.Combobox)

# Ipywidget Controller
Controller = IHP(ipw.Controller)

# Ipywidget Upload
FileUpload = IHP(ipw.FileUpload, add_css_class=(CSScls.button, CSScls.button_type_main))

# Ipywidget Media
Image = IHP(ipw.Image)
Video = IHP(ipw.Video)
Audio = IHP(ipw.Audio)

# Ipywidget Tags input
TagsInput = IHP(ipw.TagsInput)
ColorsInput = IHP(ipw.ColorsInput)
FloatsInput = IHP(ipw.FloatsInput)
IntsInput = IHP(ipw.IntsInput)


TextareaValidate = IHP(menubox.widgets.TextareaValidate, defaults={"value": ""})
ComboboxValidate = IHP(menubox.widgets.ComboboxValidate, defaults={"value": ""})
TextValidate = IHP(menubox.widgets.TextValidate, defaults={"value": ""})
FloatTextValidate = IHP(menubox.widgets.FloatTextValidate, defaults={"value": 0})
IntTextValidate = IHP(menubox.widgets.IntTextValidate, defaults={"value": 0})
SelectMultipleValidate = IHP(menubox.widgets.SelectMultipleValidate, defaults={"value": ()})
MarkdownViewer = IHP(menubox.widgets.MarkdownViewer)
# ipylab

Panel = IHP(ipylab.Panel)
SplitPanel = IHP(ipylab.SplitPanel)
CodeEditor = IHP(ipylab.CodeEditor)
SimpleOutput = IHP(ipylab.SimpleOutput)

# menubox

Menubox = IHP(cast(type["menubox.menubox.Menubox"], "menubox.menubox.Menubox"))
MenuboxVT = IHP(cast(type["menubox.menuboxvt.MenuboxVT"], "menubox.menubox.MenuboxVT"))

AsyncRunButton = IHP(
    cast(type["menubox.async_run_button.AsyncRunButton"], "menubox.async_run_button.AsyncRunButton"),
    defaults={"tasktype": mb_async.TaskType.general},
    add_css_class=CSScls.button_type_main,
)
AsyncRunButton_update = IHP(
    cast(type["menubox.async_run_button.AsyncRunButton"], "menubox.async_run_button.AsyncRunButton"),
    defaults={"tasktype": mb_async.TaskType.update},
    add_css_class=CSScls.button_type_main,
)
Modalbox = IHP(cast(type["menubox.modalbox.Modalbox"], "menubox.modalbox.Modalbox"))

Repository = IHP(
    cast(type["menubox.repository.Repository"], "menubox.repository.Repository"),
    create=lambda config: config["parent"].home.repository,  # type: ignore
    on_replace_close=False,
    set_parent=False,
    read_only=False,
)
Repositories = IHP(
    cast(type["menubox.repository.Repositories"], "menubox.repository.Repositories"),
    set_parent=False,
    dynamic_kwgs={"home": "home"},
    on_replace_close=False,
)
SelectRepository = IHP(cast(type["menubox.repository.SelectRepository"], "menubox.repository.SelectRepository"))

# other
Task: Callable[..., InstanceHP[asyncio.Task | None]] = IHP(asyncio.Task, allow_none=True, load_default=False)
