from __future__ import annotations

import enum
import os

from ipylab.css_stylesheet import CSSStyleSheet

PREFIX = f"menubox-{os.getpid()}"
V_PREFIX = f"--{PREFIX}"


class CSSvar(enum.StrEnum):
    "CSS variables available in the css stylesheet."

    button_main_color = f"{V_PREFIX}-button-main-color"
    button_menu_color = f"{V_PREFIX}-button-menu-color"
    button_open_color = f"{V_PREFIX}-button-open-color"
    button_modal_color = f"{V_PREFIX}-button-modal-color"
    button_cancel_color = f"{V_PREFIX}-button-warning-color"
    button_dangerous_color = f"{V_PREFIX}-button-dangerous-color"
    button_toggle_color = f"{V_PREFIX}-button-toggle-color"
    button_shuffle_color = f"{V_PREFIX}-button-shuffle-color"
    button_tab_color = f"{V_PREFIX}-button-tab-color"

    button_main_background_color = f"{V_PREFIX}-button-main-background-color"
    button_menu_background_color = f"{V_PREFIX}-button-menu-background-color"
    button_open_background_color = f"{V_PREFIX}-button-open-background-color"
    button_modal_background_color = f"{V_PREFIX}-button-modal-background-color"
    button_cancel_background_color = f"{V_PREFIX}-button-warning-background-color"
    button_dangerous_background_color = f"{V_PREFIX}-button-dangerous-background-color"
    button_toggle_background_color = f"{V_PREFIX}-button-toggle-background-color"
    button_shuffle_background_color = f"{V_PREFIX}-button-shuffle-background-color"
    button_tab_background_color = f"{V_PREFIX}-button-tab-background-color"

    button_busy_border = f"{V_PREFIX}-button-busy-border"
    button_active_view_border = f"{V_PREFIX}-active-view"

    menubox_border = f"{V_PREFIX}-Menubox-border"
    menubox_vt_border = f"{V_PREFIX}-MenuboxVT-border"


class CSScls(enum.StrEnum):
    "CSS class names to use in the css stylesheet."

    resize_both = f"{PREFIX}-resize-both"
    resize_horizontal = f"{PREFIX}-resize-horizontal"
    resize_vertical = f"{PREFIX}-resize-vertical"

    tab_button = f"{PREFIX}-tab-button"

    Menubox = f"{PREFIX}-Menubox"
    Menubox_header = f"{PREFIX}-Menubox-header"
    Menubox_center = f"{PREFIX}-Menubox-center"
    Menubox_menu = f"{PREFIX}-Menubox-menu"
    Menubox_shuffle = f"{PREFIX}-Menubox-shuffle"

    MenuboxVT = f"{PREFIX}-MenuboxVT"

    Modalbox = f"{PREFIX}-Modalbox"
    ModalboxHeader = f"{PREFIX}-Modalbox-header"

    button = f"{PREFIX}-button"
    button_type_modal = "mod-modal"
    button_type_main = "mod-main"
    button_type_menu = "mod-menu"
    button_type_open = "mod-open"
    button_type_tab = "mod-tab"
    button_type_cancel = "mod-cancel"
    button_type_dangerous = "mod-dangerous"
    button_type_toggle = "mod-toggle"
    button_type_shuffle = "mod-shuffle"

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
.{CSScls.resize_both} {{ resize: both;}}
.{CSScls.resize_horizontal} {{ resize: horizontal;}}
.{CSScls.resize_vertical} {{ resize: vertical;}}

.{CSScls.button} {{width: max-content; flex: 0 0 auto;}}

.{CSScls.button}.{CSScls.button_type_main} {{
    color: var({CSSvar.button_main_color});
    background-color: var({CSSvar.button_main_background_color});
}}
.{CSScls.button}.{CSScls.button_type_menu} {{
    color: var({CSSvar.button_menu_color});
    background-color: var({CSSvar.button_menu_background_color});
}}
.{CSScls.button}.{CSScls.button_type_open} {{
    color: var({CSSvar.button_open_color});
    background-color: var({CSSvar.button_open_background_color});
}}
.{CSScls.button}.{CSScls.button_type_modal} {{
    color: var({CSSvar.button_modal_color});
    background-color: var({CSSvar.button_modal_background_color});
}}
.{CSScls.button}.{CSScls.button_type_cancel} {{
    color: var({CSSvar.button_cancel_color});
    background-color: var({CSSvar.button_cancel_background_color});
}}
.{CSScls.button}.{CSScls.button_type_dangerous} {{
    color: var({CSSvar.button_dangerous_color});
    background-color: var({CSSvar.button_dangerous_background_color});
}}
.{CSScls.button}.{CSScls.button_type_toggle} {{
    color: var({CSSvar.button_toggle_color});
    background-color: var({CSSvar.button_toggle_background_color});
}}
.{CSScls.button}.{CSScls.button_type_shuffle} {{
    color: var({CSSvar.button_shuffle_color});
    background-color: var({CSSvar.button_shuffle_background_color});
}}
.{CSScls.button}.{CSScls.button_type_tab} {{
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
.{CSScls.Menubox_header} {{
    flex: 0 0 auto;
    flex-flow: row wrap;
    height: max-content;
    border-bottom: var({CSSvar.menubox_border});}}
.{CSScls.Menubox_center} {{
    height: auto;}}
.{CSScls.Menubox_menu} {{
    flex: 0 0 auto;
    flex-flow: row wrap;
    height: max-content;}}
.{CSScls.Menubox_shuffle} {{
    align-self: flex-start;
    flex-flow: row wrap;
    max-width:100%;
    height: auto;}}
.{CSScls.Modalbox}{{
    flex: 0 0 auto;
    align-self: flex-start;
    overflow: hidden;
    border: {CSSvar.menubox_border}}}
.{CSScls.MenuboxVT} {{
    border: var({CSSvar.menubox_vt_border});}}
.{CSScls.ModalboxHeader} {{
    flex: 0 0 auto;
    flex-flow: row wrap;
    border: var({CSSvar.menubox_border});}}
.{CSScls.nested_borderbox} {{
    margin: 5px 5px 5px 5px;
    padding: 5px 5px 5px 5px;
    border: var({CSSvar.menubox_border});}}
"""


class MenuboxCSSStyleSheet(CSSStyleSheet):
    SINGLE = True

    def load_stylesheet(self, text: str, variables: dict[CSSvar, str]):
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
        stylesheet.replace(text)


stylesheet = MenuboxCSSStyleSheet()


def load_stylesheet(stylesheet: MenuboxCSSStyleSheet):
    import menubox

    variables = {}
    ss = ""
    for s, v in reversed(menubox.plugin_manager.hook.add_css_stylesheet()):
        ss += s
        variables.update(v)
    stylesheet.load_stylesheet(ss, variables)
    stylesheet.on_ready(load_stylesheet, remove=True)


stylesheet.on_ready(load_stylesheet)
