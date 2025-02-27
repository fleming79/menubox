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
from menubox.defaults import NO_VALUE
from menubox.instance import IHPCreate, IHPDlinkType, InstanceHP
from menubox.instance import IHPDlinkType as DLink
from menubox.instance import instanceHP_wrapper as IHP
from menubox.stylesheet import CSScls

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "AsyncRunButton",
    "AsyncRunButton_U",
    "Accordion",
    "Audio",
    "BoundedFloatText",
    "BoundedIntText",
    "Box",
    "MenuBoxHeader",
    "MenuBoxCenter",
    "MenuBoxMenu",
    "MenuBoxShuffle",
    "Button",
    "Button_E",
    "Button_M",
    "Button_MB",
    "Button_O",
    "Button_S",
    "Button_T",
    "Button_W",
    "Checkbox",
    "Checkbox_A",
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
    "MenuBox",
    "ModalBox",
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
Checkbox_A = IHP(
    ipw.Checkbox,
    defaults={
        "layout": {"width": "auto"},
        "style": {"description_width": "initial"},
    },
)
ToggleButton = IHP(ipw.ToggleButton)
Valid = IHP(ipw.Valid)

# Ipywidget Button
Button = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_main))
Button_O = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_open))
Button_W = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_warning))
Button_E = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_dangerous))
Button_MB = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_modal))
Button_M = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_menu))
Button_T = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_toggle))
Button_S = IHP(ipw.Button, add_css_class=(CSScls.button, CSScls.button_shuffle))

# Ipywidget Box
Box = IHP(ipw.Box)
VBox = IHP(ipw.VBox)
HBox = IHP(ipw.HBox)
GridBox = IHP(ipw.GridBox)

MenuBoxHeader = IHP(
    ipw.HBox,
    dlink={"source": ("self", "border"), "target": "layout.border_bottom"},
    add_css_class=CSScls.MenuBoxHeader,
)
MenuBoxCenter = IHP(ipw.VBox, add_css_class=CSScls.MenuBoxCenter)
MenuBoxMenu = IHP(ipw.HBox, add_css_class=CSScls.MenuBoxMenu)
MenuBoxShuffle = IHP(ipw.HBox, add_css_class=CSScls.MenuBoxShuffle)


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
FileUpload = IHP(ipw.FileUpload, add_css_class=(CSScls.button, CSScls.button_main))

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

MenuBox = IHP(cast(type["menubox.menubox.MenuBox"], "menubox.menubox.MenuBox"))
MenuBoxVT = IHP(cast(type["menubox.menuboxvt.MenuBoxVT"], "menubox.menubox.MenuBoxVT"))

AsyncRunButton = IHP(
    cast(type["menubox.async_run_button.AsyncRunButton"], "menubox.async_run_button.AsyncRunButton"),
    defaults={"tasktype": mb_async.TaskType.general},
    add_css_class=CSScls.button_main,
)
AsyncRunButton_U = IHP(
    cast(type["menubox.async_run_button.AsyncRunButton"], "menubox.async_run_button.AsyncRunButton"),
    defaults={"tasktype": mb_async.TaskType.update},
    add_css_class=CSScls.button_main,
)
ModalBox = IHP(cast(type["menubox.modalbox.ModalBox"], "menubox.modalbox.ModalBox"))

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
