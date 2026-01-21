from __future__ import annotations

import enum
import os

from ipylab.common import Singular
from ipylab.css_stylesheet import CSSStyleSheet

PREFIX = f"menubox-{os.getpid()}"
V_PREFIX = f"--{PREFIX}"


class CSSvar(enum.StrEnum):
    "CSS variables available in the css stylesheet."

    button_main_color = f"{V_PREFIX}-button-main-color"
    button_menu_color = f"{V_PREFIX}-button-menu-color"
    button_open_color = f"{V_PREFIX}-button-open-color"
    button_modal_color = f"{V_PREFIX}-button-modal-color"
    button_cancel_color = f"{V_PREFIX}-button-cancel-color"
    button_dangerous_color = f"{V_PREFIX}-button-dangerous-color"
    button_toggle_color = f"{V_PREFIX}-button-toggle-color"
    button_shuffle_color = f"{V_PREFIX}-button-shuffle-color"
    button_activate_color = f"{V_PREFIX}-button-activate-color"
    button_tab_color = f"{V_PREFIX}-button-tab-color"

    button_main_background_color = f"{V_PREFIX}-button-main-background-color"
    button_menu_background_color = f"{V_PREFIX}-button-menu-background-color"
    button_open_background_color = f"{V_PREFIX}-button-open-background-color"
    button_modal_background_color = f"{V_PREFIX}-button-modal-background-color"
    button_cancel_background_color = f"{V_PREFIX}-button-cancel-background-color"
    button_dangerous_background_color = f"{V_PREFIX}-button-dangerous-background-color"
    button_toggle_background_color = f"{V_PREFIX}-button-toggle-background-color"
    button_shuffle_background_color = f"{V_PREFIX}-button-shuffle-background-color"
    button_activate_background_color = f"{V_PREFIX}-button-activate-background-color"
    button_tab_background_color = f"{V_PREFIX}-button-tab-background-color"

    button_busy_border = f"{V_PREFIX}-button-busy-border"
    button_active_view_border = f"{V_PREFIX}-active-view"

    menubox_border = f"{V_PREFIX}-Menubox-border"
    menubox_vt_border = f"{V_PREFIX}-MenuboxVT-border"


class CSScls(enum.StrEnum):
    "CSS class names to use in the css stylesheet."

    resize_both = "ipylab-ResizeBoth"
    resize_horizontal = "ipylab-ResizeHorizontal"
    resize_vertical = "ipylab-ResizeVertical"

    tab_button = f"{PREFIX}-tab-button"

    Menubox = f"{PREFIX}-Menubox"
    Menubox_item = f"{PREFIX}-Menubox-item"
    MenuboxVT_item = f"{PREFIX}-MenuboxVT-item"
    box_header = "mod-box-header"
    centerbox = "mod-box-center"
    box_menu = "mod-box-menu"
    box_shuffle = "mod-box-shuffle"
    wrapper = "mod-wrapper"

    MenuboxVT = f"{PREFIX}-MenuboxVT"

    Modalbox = f"{PREFIX}-Modalbox"
    ModalboxHeader = f"{PREFIX}-Modalbox-header"

    button = f"{PREFIX}-button"
    button_modal = "mod-modal"
    button_main = "mod-main"
    button_menu = "mod-menu"
    button_open = "mod-open"
    button_tab = "mod-tab"
    button_cancel = "mod-cancel"
    button_dangerous = "mod-dangerous"
    button_toggle = "mod-toggle"
    button_shuffle = "mod-shuffle"
    button_activate = "mod-activate"

    button_is_busy = "mod-button-busy"
    button_active_view = "mod-active-view"

    nested_borderbox = f"{PREFIX}-nested-border-box"  # A box using same default border as menubox

    Menubox_horizontal = "horizontal"  # A modifier applicable to menubox


VARIABLES = {
    # Colors
    CSSvar.button_main_color: "var(--jp-ui-inverse-font-color1)",
    CSSvar.button_main_background_color: "var(--jp-accept-color-normal)",
    CSSvar.button_menu_color: "var(--jp-ui-font-color1)",
    CSSvar.button_menu_background_color: "var(--jp-border-color2)",
    CSSvar.button_open_color: f"var({CSSvar.button_menu_color})",
    CSSvar.button_open_background_color: f"var({CSSvar.button_menu_background_color})",
    CSSvar.button_modal_color: f"var({CSSvar.button_menu_color})",
    CSSvar.button_modal_background_color: f"var({CSSvar.button_menu_background_color})",
    CSSvar.button_toggle_color: f"var({CSSvar.button_menu_color})",
    CSSvar.button_toggle_background_color: f"var({CSSvar.button_menu_background_color})",
    CSSvar.button_shuffle_color: f"var({CSSvar.button_menu_color})",
    CSSvar.button_shuffle_background_color: f"var({CSSvar.button_menu_background_color})",
    CSSvar.button_activate_color: "var(--jp-ui-font-color1)",
    CSSvar.button_activate_background_color: "var(--jp-border-color3)",
    CSSvar.button_tab_color: f"var({CSSvar.button_menu_color})",
    CSSvar.button_tab_background_color: f"var({CSSvar.button_menu_background_color})",
    CSSvar.button_cancel_color: "var(--jp-ui-inverse-font-color1)",
    CSSvar.button_cancel_background_color: "var(--jp-reject-color-normal)",
    CSSvar.button_dangerous_color: "var(--jp-ui-inverse-font-color2)",
    CSSvar.button_dangerous_background_color: "var(--jp-warn-color-normal)",
    # Borders
    CSSvar.button_busy_border: "solid 1px var(--jp-reject-color-normal)",
    CSSvar.button_active_view_border: "solid 2px var(--jp-border-color1)",
    CSSvar.menubox_border: "solid 1px var(--jp-border-color3)",
    CSSvar.menubox_vt_border: "solid 1px var(--jp-border-color2)",
}

STYLESHEET = f"""
.{CSScls.button} {{width: max-content; flex: 0 0 auto;}}

.{CSScls.button}.{CSScls.button_main} {{
    color: var({CSSvar.button_main_color});
    background-color: var({CSSvar.button_main_background_color});
}}
.{CSScls.button}.{CSScls.button_menu} {{
    color: var({CSSvar.button_menu_color});
    background-color: var({CSSvar.button_menu_background_color});
}}
.{CSScls.button}.{CSScls.button_open} {{
    color: var({CSSvar.button_open_color});
    background-color: var({CSSvar.button_open_background_color});
}}
.{CSScls.button}.{CSScls.button_modal} {{
    color: var({CSSvar.button_modal_color});
    background-color: var({CSSvar.button_modal_background_color});
}}
.{CSScls.button}.{CSScls.button_cancel} {{
    color: var({CSSvar.button_cancel_color});
    background-color: var({CSSvar.button_cancel_background_color});
}}
.{CSScls.button}.{CSScls.button_dangerous} {{
    color: var({CSSvar.button_dangerous_color});
    background-color: var({CSSvar.button_dangerous_background_color});
}}
.{CSScls.button}.{CSScls.button_toggle} {{
    color: var({CSSvar.button_toggle_color});
    background-color: var({CSSvar.button_toggle_background_color});
}}
.{CSScls.button}.{CSScls.button_shuffle} {{
    color: var({CSSvar.button_shuffle_color});
    background-color: var({CSSvar.button_shuffle_background_color});
}}
.{CSScls.button}.{CSScls.button_activate} {{
    color: var({CSSvar.button_activate_color});
    background-color: var({CSSvar.button_activate_background_color});
}}
.{CSScls.button}.{CSScls.button_tab} {{
    color: var({CSSvar.button_tab_color});
    background-color: var({CSSvar.button_tab_background_color});
}}

.{CSScls.button}.{CSScls.button_is_busy} {{
    border: var({CSSvar.button_busy_border});
    box-shadow: 0 4px 5px 0 rgba(0, 0, 0, var(--md-shadow-key-penumbra-opacity)),
    0 1px 10px 0 rgba(0, 0, 0, var(--md-shadow-ambient-shadow-opacity)),
    0 2px 4px -1px rgba(0, 0, 0, var(--md-shadow-key-umbra-opacity));
}}
.{CSScls.button}.{CSScls.button_active_view} {{
    border: var({CSSvar.button_active_view_border});
}}

/* Boxes */
.{CSScls.Menubox} {{
    border: var({CSSvar.menubox_border});}}
.{CSScls.Menubox}.horizontal {{
    flex-flow: row wrap;}}
.{CSScls.Menubox_item}.{CSScls.box_header} {{
    flex: 0 0 auto;
    flex-flow: row wrap;
    height: max-content;
    border-bottom: var({CSSvar.menubox_border});}}
.{CSScls.Menubox_item}.{CSScls.centerbox} {{
    flex: 1 0 auto;
    height: auto;}}
.{CSScls.Menubox_item}.{CSScls.box_menu} {{
    flex: 0 1 auto;
    flex-flow: row wrap;}}
.{CSScls.Menubox_item}.{CSScls.box_shuffle} {{
    flex-flow: row wrap;
    border: {CSSvar.menubox_border};
    align-self: flex-start;
    max-width:100%;
    height: auto;}}

.{CSScls.Menubox}.{CSScls.wrapper} {{
    border: var({CSSvar.menubox_vt_border});
    margin: 5px 5px 5px 5px;}}

.{CSScls.MenuboxVT} {{
    border: var({CSSvar.menubox_vt_border});}}
.{CSScls.MenuboxVT_item}.{CSScls.box_header} {{
    flex: 0 0 auto;
    flex-flow: row wrap;
    height: max-content;
    border-bottom: var({CSSvar.menubox_vt_border});}}
.{CSScls.Modalbox}{{
    flex: 0 0 auto;
    align-self: flex-start;
    overflow: hidden;
    border: var({CSSvar.menubox_border});}}
.{CSScls.ModalboxHeader} {{
    flex: 0 0 auto;
    flex-flow: row wrap;
    border: var({CSSvar.menubox_border});}}
.{CSScls.nested_borderbox} {{
    flex: 0 0 auto;
    margin: 5px;
    padding: 0px;
    border: var({CSSvar.menubox_border});}}
"""


class MenuboxCSSStyleSheet(Singular, CSSStyleSheet):
    async def load_stylesheet(self, text: str, variables: dict[CSSvar, str]):
        """Loads a stylesheet with the given text and variables.

        The stylesheet text will have the `VARIABLES_KEY` replaced with the
        given variables. The variables are combined with the default `VARIABLES`.

        Args:
            text: The stylesheet text.
            variables: A dictionary of CSS variables to values.
        """
        variables = VARIABLES | variables
        variables_ = f":root {{{''.join(f'{k} :{v};\n' for k, v in variables.items())}}}\n"
        text = variables_ + text
        await self.replace(text)
