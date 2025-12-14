from __future__ import annotations

from typing import TYPE_CHECKING

import ipylab

from menubox.css import STYLESHEET
from menubox.defaults import hookimpl

if TYPE_CHECKING:
    from ipylab.css_stylesheet import CSSStyleSheet

    from menubox import Menubox


stylesheet: CSSStyleSheet | None = None


@hookimpl
def add_css_stylesheet():
    return STYLESHEET, {
        "--jp-widgets-input-background-color": "var(--jp-input-background)",
        "--jp-widgets-input-focus-border-color": "var(--jp-input-active-border-color)",
        "--jp-widgets-input-border-width": "var(--jp-border-width)",
    }


@hookimpl
def get_icon(obj: Menubox):
    return ipylab.Icon()
