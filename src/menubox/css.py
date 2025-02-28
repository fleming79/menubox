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

    button_main_background_color = f"{V_PREFIX}-button-main-background-color"
    button_menu_background_color = f"{V_PREFIX}-button-menu-background-color"
    button_open_background_color = f"{V_PREFIX}-button-open-background-color"
    button_modal_background_color = f"{V_PREFIX}-button-modal-background-color"
    button_cancel_background_color = f"{V_PREFIX}-button-warning-background-color"
    button_dangerous_background_color = f"{V_PREFIX}-button-dangerous-background-color"
    button_toggle_background_color = f"{V_PREFIX}-button-toggle-background-color"
    button_shuffle_background_color = f"{V_PREFIX}-button-shuffle-background-color"

    button_busy_border = f"{V_PREFIX}-button-busy-border"
    button_active_view_border = f"{V_PREFIX}-button-busy-border"

    menubox_border = f"{V_PREFIX}-Menubox-border"
    menubox_vt_border = f"{V_PREFIX}-MenuboxVT-border"


class CSScls(enum.StrEnum):
    "CSS class names to use in the css stylesheet."

    resize_both = f"{PREFIX}-resize-both"
    resize_horizontal = f"{PREFIX}-resize-horizontal"
    resize_vertical = f"{PREFIX}-resize-vertical"

    tab_button = f"{PREFIX}-tab-button"

    Menubox = f"{PREFIX}-Menubox"
    MenuboxHeader = f"{PREFIX}-Menubox-header"
    MenuboxCenter = f"{PREFIX}-Menubox-center"
    MenuboxMenu = f"{PREFIX}-Menubox-menu"
    MenuboxShuffle = f"{PREFIX}-Menubox-shuffle"

    MenuboxVT = f"{PREFIX}-MenuboxVT"

    ModalBoxHeader = f"{PREFIX}-ModalBox-header"

    button = f"{PREFIX}-button"
    button_modal = f"{PREFIX}-button-modal"
    button_main = f"{PREFIX}-button-main"
    button_menu = f"{PREFIX}-button-menu"
    button_open = f"{PREFIX}-button-open"
    button_cancel = f"{PREFIX}-button-cancel"
    button_dangerous = f"{PREFIX}-button-dangerous"
    button_toggle = f"{PREFIX}-button-toggle"
    button_shuffle = f"{PREFIX}-button-shuffle"

    button_is_busy = f"{PREFIX}-button-busy"
    button_active_view = f"{PREFIX}-button-active_view"

    async_run_button = f"{PREFIX}-async_run_button"


VARIABLES = {
    CSSvar.button_main_color: "var(--jp-ui-inverse-font-color1)",
    CSSvar.button_main_background_color: "var(--jp-accept-color-normal)",
    CSSvar.button_menu_color: "var(--jp-ui-font-color2)",
    CSSvar.button_menu_background_color: "var(--jp-border-color2)",
    CSSvar.button_open_color: f"var({CSSvar.button_menu_color})",
    CSSvar.button_open_background_color: f"var({CSSvar.button_menu_background_color})",
    CSSvar.button_modal_color: f"var({CSSvar.button_menu_color})",
    CSSvar.button_modal_background_color: f"var({CSSvar.button_menu_background_color})",
    CSSvar.button_toggle_color: f"var({CSSvar.button_menu_color})",
    CSSvar.button_toggle_background_color: f"var({CSSvar.button_menu_background_color})",
    CSSvar.button_shuffle_color: f"var({CSSvar.button_menu_color})",
    CSSvar.button_shuffle_background_color: f"var({CSSvar.button_menu_background_color})",
    CSSvar.button_cancel_color: "var(--jp-ui-inverse-font-color1)",
    CSSvar.button_cancel_background_color: "var(--jp-reject-color-normal)",
    CSSvar.button_dangerous_color: "var(--jp-ui-inverse-font-color2)",
    CSSvar.button_dangerous_background_color: "var(--jp-warn-color-normal)",
    CSSvar.button_busy_border: "var(--jp-border-color1)",
    CSSvar.button_active_view_border: "var(--jp-border-color1)",
    CSSvar.menubox_border: "solid 1px var(--jp-border-color3)",
    CSSvar.menubox_vt_border: "solid 1px var(--jp-border-color2)",
}

VARIABLES_KEY = "VARIABLES"
STYLESHEET = f"""
:root {{
--jp-widgets-color: var(--jp-content-font-color1);
--jp-widgets-label-color: var(--jp-widgets-color);
--jp-widgets-readout-color: var(--jp-widgets-color);
--jp-widgets-input-color: var(--jp-ui-font-color1);
--jp-widgets-input-background-color: var(--jp-input-background);
--jp-widgets-input-border-color: var(--jp-border-color1);
--jp-widgets-input-focus-border-color: var(--jp-input-active-border-color);
--jp-widgets-input-border-width: var(--jp-border-width);
{VARIABLES_KEY}
}}

.{CSScls.resize_both} {{ resize: both;}}
.{CSScls.resize_horizontal} {{ resize: horizontal;}}
.{CSScls.resize_vertical} {{ resize: vertical;}}

.{CSScls.button} {{width: max-content; flex: 0 0 auto;}}

.{CSScls.button_main} {{
    color: var({CSSvar.button_main_color});
    background-color: var({CSSvar.button_main_background_color});
}}
.{CSScls.button_menu} {{
    color: var({CSSvar.button_menu_color});
    background-color: var({CSSvar.button_menu_background_color});
}}
.{CSScls.button_open} {{
    color: var({CSSvar.button_open_color});
    background-color: var({CSSvar.button_open_background_color});
}}
.{CSScls.button_modal} {{
    color: var({CSSvar.button_modal_color});
    background-color: var({CSSvar.button_modal_background_color});
}}
.{CSScls.button_cancel} {{
    color: var({CSSvar.button_cancel_color});
    background-color: var({CSSvar.button_cancel_background_color});
}}
.{CSScls.button_dangerous} {{
    color: var({CSSvar.button_dangerous_color});
    background-color: var({CSSvar.button_dangerous_background_color});
}}
.{CSScls.button_toggle} {{
    color: var({CSSvar.button_toggle_color});
    background-color: var({CSSvar.button_toggle_background_color});
}}
.{CSScls.button_shuffle} {{
    color: var({CSSvar.button_shuffle_color});
    background-color: var({CSSvar.button_shuffle_background_color});
}}
.{CSScls.button_is_busy} {{
    border: var({CSSvar.button_busy_border});
    box-shadow: 0 4px 5px 0 rgba(0, 0, 0, var(--md-shadow-key-penumbra-opacity)),
    0 1px 10px 0 rgba(0, 0, 0, var(--md-shadow-ambient-shadow-opacity)),
    0 2px 4px -1px rgba(0, 0, 0, var(--md-shadow-key-umbra-opacity));
}}
.{CSScls.button_active_view} {{
    border: var({CSSvar.button_active_view_border});
}}

/* Boxes */
.{CSScls.Menubox} {{
    flex: 1 0 auto;
    border: var({CSSvar.menubox_border});}}
.{CSScls.MenuboxHeader} {{
    flex: 0 0 auto;
    flex-flow: row wrap;
    height: max-content;
    border: var({CSSvar.menubox_border});}}
.{CSScls.MenuboxCenter} {{
    flex: 1 0 auto;}}
.{CSScls.MenuboxMenu} {{
    flex: 0 0 auto;
    flex-flow: row wrap;
    height: max-content;}}
.{CSScls.MenuboxShuffle} {{
    flex: 0 0 auto;
    flex-flow: row wrap;
    height: max-content;}}
.{CSScls.Menubox} {{
    border: var({CSSvar.menubox_vt_border});}}
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
        variables_ = "".join(f"{k} :{v};\n" for k, v in variables.items())
        text = text.replace(VARIABLES_KEY, variables_)
        stylesheet.replace(text)


stylesheet = MenuboxCSSStyleSheet()


def load_stylesheet(stylesheet: MenuboxCSSStyleSheet):
    import menubox

    stylesheet.load_stylesheet(*menubox.plugin_manager.hook.get_css_stylesheet_and_variables())
    stylesheet.on_ready(load_stylesheet, remove=True)


stylesheet.on_ready(load_stylesheet)
