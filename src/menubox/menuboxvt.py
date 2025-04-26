from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Self, cast, override

import ipylab
import ipywidgets as ipw
import traitlets

import menubox as mb
from menubox import trait_factory as tf
from menubox import utils
from menubox.css import CSScls
from menubox.menubox import Menubox
from menubox.pack import load_yaml, to_yaml
from menubox.trait_types import RP, ChangeType, GetWidgetsInputType, StrTuple
from menubox.valuetraits import ValueTraits
from menubox.widgets import ComboboxValidate, MarkdownOutput

_template_folders: set[pathlib.Path] = set()

if TYPE_CHECKING:
    from menubox.repository import Repository  # noqa: F401

__all__ = ["MenuboxVT"]


class MenuboxVT(ValueTraits, Menubox, Generic[RP]):
    """
    MenuboxVT Combines Menubox with ValueTraits and provides additional features such as templates,
    copy/paste settings, configuration view and description rendering.

    Create subclasses from this class.
    """

    SHOW_TEMPLATE_CONTROLS = False
    CONFIGURE_VIEW = "Configure"
    DESCRIPTION_VIEWER_TEMPLATE = (
        "<details {details_open}><summary><b>Description</b></summary>\n\n{description}\n</details>"
    )
    FANCY_NAME = ""
    RESERVED_VIEWNAMES = (*Menubox.RESERVED_VIEWNAMES, CONFIGURE_VIEW)
    title_description = traitlets.Unicode("<b>{self.FANCY_NAME or self.__class__.__qualname__}&emsp;{self.name}</b>")
    title_description_tooltip = traitlets.Unicode("{self.description.value or utils.fullname(self.__class__)}")
    header_right_children = StrTuple("_get_template_controls", "button_configure", *Menubox.header_right_children)
    css_classes = StrTuple(CSScls.Menubox, CSScls.MenuboxVT)
    _description_params: ClassVar[dict[str, Any]] = {"details_open": ""}

    if TYPE_CHECKING:
        parent: tf.InstanceHP[Self, RP, RP]

    header = (
        tf.MenuboxHeader()
        .hooks(
            add_css_class=(CSScls.MenuboxVT_item, CSScls.box_header),
        )
        .configure(tf.IHPMode.XLRN)
    )
    _sw_template = tf.Dropdown(
        value=None, description="Templates", style={"description_width": "initial"}, layout={"width": "max-content"}
    )
    _mb_refresh_traitnames = (*Menubox._mb_refresh_traitnames, "button_configure")
    box_template_controls = tf.InstanceHP(
        cast(Self, 0), klass=ipw.HBox, default=lambda _: ipw.HBox(layout={"width": "max-content"})
    ).hooks(
        set_children=lambda p: (
            p.button_clip_put,
            p.button_paste,
            p._sw_template,
            p._button_load_template,
            p._button_template_info,
        )
    )
    template_controls = tf.Modalbox(
        cast(Self, 0),
        obj=lambda p: p.box_template_controls,
        title="Copy and load settings",
        button_expand_description="📜",
        button_expand_tooltip="Templates for and copy/paste settings for {self.FANCY_NAME} {self.__class__.__qualname__}.",
        on_expand=lambda p: p._on_template_controls_expand(),
    ).configure(tf.IHPMode.XLRN)
    text_name = tf.InstanceHP(
        cast(Self, 0),
        klass=ComboboxValidate,
        default=lambda c: ComboboxValidate(
            validate=c["parent"]._validate_name,
            description="Name",
            continuous_update=False,
            layout={"width": "auto", "flex": "1 0 auto", "min_width": "100px", "max_width": "600px"},
            style={"description_width": "initial"},
        ),
    ).hooks(
        on_set=lambda c: (
            c["parent"].link(source=(c["parent"], "name"), target=(c["obj"], "value")),
            c["parent"].dlink(
                source=(c["parent"], "name"),
                target=(c["obj"], "disabled"),
                transform=lambda name: bool(not c["parent"].RENAMEABLE if name else False),
            ),
        ),
    )
    description_preview_label = tf.HTML(value="<b>Description preview</b>")
    description = tf.CodeEditor(description="Description", mime_type="text/x-markdown")
    description_viewer = tf.InstanceHP(
        cast(Self, 0),
        klass=MarkdownOutput,
        default=lambda c: MarkdownOutput(
            layout={"margin": "0px 0px 0px 10px"},
            converter=c["parent"]._convert_description,
        ).add_class(CSScls.resize_vertical),
    ).hooks(
        on_set=lambda c: c["parent"].dlink(
            source=(c["parent"].description, "value"),
            target=(c["obj"], "value"),
        )
    )
    button_configure = (
        tf.Button_open(cast(Self, 0), tooltip="Configure")
        .hooks(
            on_set=lambda c: c["parent"].dlink(
                source=(c["parent"], "view"),
                target=(c["obj"], "description"),
                transform=lambda view: "End configure" if view == MenuboxVT.CONFIGURE_VIEW else "🔧",
            ),
        )
        .configure(tf.IHPMode.X_RN)
    )
    button_clip_put = tf.Button_open(description="📎", tooltip="Copy settings to clipboard")
    button_paste = tf.Button_open(description="📋", tooltip="Paste settings from clipboard\n")
    _button_load_template = tf.Button_main(
        description="Load",
        tooltip="Overwrite existing settings with template.\nExisting settings will be overwritten without warning.",
    )
    _button_template_info = tf.Button_main(
        description="Info", tooltip="Show template details in a read only text editor."
    )
    subpath = tf.ComboboxValidate(
        validate=utils.sanatise_filename,
        description="Subpath",
        value="",
        tooltip="The subpath relative to the current repository",
        layout={"width": "auto", "flex": "1 0 auto", "min_width": "100px"},
    )

    def __init_subclass__(cls, **kwargs) -> None:
        if getattr(mb, "DEBUG_ENABLED", True):
            mro = cls.mro()
            if mro.index(ValueTraits) < mro.index(__class__):
                smo = "\n\t".join(o.__qualname__ for o in cls.mro())
                msg = (
                    f"{cls} is a subclass of {__class__} and {ValueTraits}."
                    f"\nHowever the mro reports that {__class__} is lower in the list"
                    f" than {ValueTraits} which may cause"
                    f"unexpected behaviour.\nRevise the list of inheritance of {cls}"
                    f" so {__class__} is above {ValueTraits} in the mro.\n"
                    f"Current mro: {smo}"
                )
                raise TypeError(msg)
        super().__init_subclass__(**kwargs)

    def _get_template_controls(self):
        if self.SHOW_TEMPLATE_CONTROLS:
            return self.template_controls
        return None

    def _on_template_controls_expand(self):
        if getattr(self, "_n_template_folders", 0) != len(_template_folders):
            self.update_templates()
        self._sw_template.options = self.templates

    @staticmethod
    def register_template_root_folder(folder: pathlib.Path):
        """Register a root folder that contains folders of yaml templates by MenuboxVT
        subclass names.

        |templates root folder
        |-Subclass Folder
        |--template_name.yaml
        """
        folder = pathlib.Path(folder).absolute()
        if not folder.is_dir():
            msg = f"Template folder not found '{folder}'!"
            raise NotADirectoryError(msg)
        _template_folders.add(folder)

    register_template_root_folder(pathlib.Path(__file__).parent.joinpath("templates"))

    @property
    def templates(self) -> dict:
        """Templates for the class will be available in this dict mapping a name to
        dict of the settings.

        The settings can be defined as yaml files in the _template_folder.
        """
        cls = self.__class__
        if not hasattr(cls, "_templates"):
            cls.update_templates()
        return cls._templates

    @classmethod
    def update_templates(cls):
        cls._templates = {}
        for root in _template_folders:
            folder = root.joinpath(cls.__qualname__)
            if folder.exists():
                for f in folder.glob("*"):
                    if f.is_file() and f.suffix in [".yaml", ".json"]:
                        cls._templates[f.stem] = f
        cls._n_template_folders = len(_template_folders)

    @override
    async def button_clicked(self, b: ipw.Button):
        await super().button_clicked(b)
        match b:
            case self._button_load_template:
                if self._sw_template.value:
                    self.set_trait("value", self._sw_template.value)
                    if self.template_controls:
                        self.template_controls.collapse()
            case self._button_template_info:
                await self._show_template_info()
            case self.button_clip_put:
                self.to_clipboard()
            case self.button_paste:
                self.from_clipboard()
            case self.button_configure:
                if self.view == self.CONFIGURE_VIEW:
                    view = self.view_previous
                    if view == self.CONFIGURE_VIEW:
                        view = self._current_views[0]
                else:
                    view = self.CONFIGURE_VIEW
                self.load_view(view)

    def _convert_description(self, value: str):
        if value:
            value = self.fstr(value)
            parameters = self._description_params | {"description": value}
            if self.view == self.CONFIGURE_VIEW:
                parameters["details_open"] = "open"
            return self.fstr(self.DESCRIPTION_VIEWER_TEMPLATE, parameters=parameters)
        return ""

    async def _show_template_info(self):
        if self._sw_template.value:
            path = self._sw_template.value
            if isinstance(path, pathlib.Path):
                with path.open() as f:
                    data = f.read()
                mime_type = "text/json" if path.suffix == "json" else "text/yaml"
                await self.app.dialog.show_dialog(
                    title=path.name, body=ipylab.CodeEditor(value=data, mime_type=mime_type)
                )

    @override
    async def get_center(self, view: str | None) -> tuple[str | None, GetWidgetsInputType[RP]]:
        if view == self.CONFIGURE_VIEW:
            return view, (self.text_name, self.description, self.description_viewer)
        return await super().get_center(view)

    def from_clipboard(self):
        from pandas.io.clipboard import clipboard_get  # type: ignore

        self.set_trait("value", load_yaml(clipboard_get()))

    def to_clipboard(self):
        from pandas.io.clipboard import clipboard_set  # type: ignore

        clipboard_set(to_yaml(self.value(), walkstring=True))

    @override
    def on_change(self, change: ChangeType):
        super().on_change(change)
        if change["name"] == "visibility" and self.view:
            self.mb_refresh()
