# ruff: noqa: F401

import inspect

import ipywidgets
from ipywidgets import *  # noqa: F403  # pyright: ignore[reportWildcardImportFromLibrary]
from ipywidgets.widgets.widget_description import DescriptionStyle

try:
    from ipywidgets.widgets.widget_int import ProgressStyle, SliderStyle
    from ipywidgets.widgets.widget_string import (
        HTMLMathStyle,
        HTMLStyle,
        LabelStyle,
        TextStyle,
    )
except ImportError:
    pass

all_widget_classes = {}
for k in dir(ipywidgets):
    m = getattr(ipywidgets, k)
    if inspect.isclass(m) and issubclass(m, ipywidgets.Widget):
        all_widget_classes[k] = m


def widget_from_string(string):
    """Create a widget from its string representation."""

    inst = eval(string, all_widget_classes)
    if not isinstance(inst, ipywidgets.Widget):
        msg = f"Expected a widget but got {inst.__class__} from {string=}"
        raise TypeError(msg)
    return inst
