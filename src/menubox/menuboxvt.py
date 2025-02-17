from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING, Any, ClassVar

import ipylab
import ipywidgets as ipw
import traitlets

import menubox as mb
from menubox import trait_factory as tf
from menubox import utils
from menubox.menubox import MenuBox
from menubox.pack import load_yaml, to_yaml
from menubox.trait_types import ChangeType, NameTuple, StrTuple, classproperty
from menubox.valuetraits import ValueTraits

_template_folders: set[pathlib.Path] = set()

if TYPE_CHECKING:
    import ipywidgets as ipw

    from menubox.modalbox import ModalBox
    from menubox.repository import Repository

__all__ = ["MenuBoxVT"]


class MenuBoxVT(MenuBox, ValueTraits):
    """
    MenuBoxVT Combines Menubox with ValueTraits and provides additional features such as templates,
    copy/paste settings, configuration view and description rendering.

    Create subclasses from this class.
    """

    SHOW_TEMPLATE_CONTROLS = False
    _CONFIGURE_VIEW = "Configure"
    DESCRIPTION_VIEWER_TEMPLATE = (
        "<details {details_open}><summary><b>Description</b></summary>\n\n{description}\n</details>"
    )
    FANCY_NAME = ""
    _RESERVED_VIEWNAMES = (*MenuBox._RESERVED_VIEWNAMES, _CONFIGURE_VIEW)
    repository: traitlets.Instance[Repository] = traitlets.Instance("menubox.repository.Repository")
    title_description = traitlets.Unicode("<b>{self.FANCY_NAME or self.__class__.__name__}&emsp;{self.name}</b>")
    title_description_tooltip = traitlets.Unicode("{self.description.value or utils.fullname(self.__class__)}")
    header_right_children = StrTuple("_get_template_controls", "button_configure", *MenuBox.header_right_children)
    _templates = traitlets.Dict(traitlets.Unicode(), traitlets.Unicode())
    _description_params: ClassVar[dict[str, Any]] = {"details_open": ""}
    _sw_template = tf.Dropdown(
        value=None, description="Templates", style={"description_width": "initial"}, layout={"width": "max-content"}
    )
    box_template_controls = tf.HBox(layout={"width": "max-content"}).set_children(
        "button_clip_put", "button_paste", "_sw_template", "_button_load_template", "_button_template_info"
    )
    _mb_refresh_traitnames = (*MenuBox._mb_refresh_traitnames, "button_configure")
    template_controls = tf.ModalBox(
        "box_template_controls",
        title="Copy and load settings",
        button_expand_description="📜",
        button_expand_tooltip="Templates for and copy/paste settings for {self.FANCY_NAME} {self.__class__.__name__}.",
        on_expand="_on_template_controls_expand",
    ).configure(
        allow_none=True,
    )
    text_name = tf.Text(
        description="Name",
        continuous_update=False,
        layout={"width": "auto", "flex": "1 0 auto", "min_width": "100px", "max_width": "600px"},
        style={"description_width": "initial"},
    ).configure(
        dynamic_kwgs={"value": "name", "disabled": lambda config: config["parent"].RENAMEABLE},
    )
    _description_label = tf.HTML("<b>Description</b>")
    _description_preview_label = tf.HTML("<b>Description preview</b>")
    _box_edit_description_edit = tf.VBox().set_children("_description_label", "description")
    _box_edit_description_preview = tf.VBox().set_children("_description_preview_label", "description_viewer")
    _box_edit_description = tf.HBox(layout={"justify_content": "space-between"}).set_children(
        "_box_edit_description_edit", "_box_edit_description_preview"
    )

    description = tf.CodeEditor(mime_type="text/x-markdown")
    description_viewer = tf.MarkdownViewer(layout={"margin": "0px 0px 0px 10px"}).configure(
        dlink={"source": ("description", "value"), "target": "value"},
        set_attrs={"converter": "._convert_description"},
        add_css_class=(mb.defaults.CLS_RESIZE_VERTICAL,),
    )
    button_configure = tf.Button_O(tooltip="Configure").configure(
        load_default=False,
        dlink={
            "source": ("self", "view"),
            "target": "description",
            "transform": lambda view: "End configure" if view == MenuBoxVT._CONFIGURE_VIEW else "🔧",
        },
    )
    button_clip_put = tf.Button_O(description="📎", tooltip="Copy settings to clipboard")
    button_paste = tf.Button_O(description="📋", tooltip="Paste settings from clipboard\n")
    _button_load_template = tf.Button(
        description="Load",
        tooltip="Overwrite existing settings with template.\nExisting settings will be overwritten without warning.",
    )
    _button_template_info = tf.Button(description="Info", tooltip="Show template details in a read only text editor.")
    subpath = tf.TextValidate(
        validate=utils.sanatise_filename,
        description="Subpath",
        value="",
        tooltip="The subpath relative to the current repository",
        layout={"width": "auto", "flex": "1 0 auto", "min_width": "100px"},
    )

    value_traits = NameTuple("text_name", "name", "description", "description_viewer")

    def __init_subclass__(cls, **kwargs) -> None:
        if mb.DEBUG_ENABLED:
            mro = cls.mro()
            if mro.index(ValueTraits) < mro.index(__class__):
                smo = "\n\t".join(o.__name__ for o in cls.mro())
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

    @traitlets.default("repository")
    def _default_repository(self):
        return self.home.repository

    @property
    def fs_root(self):
        return self.repository.to_path(self.get_value("subpath"))

    def __repr__(self):
        if self._MenuBox_init_complete:
            name = self.name if self.trait_has_value("name") else ""
            cs = "closed: " if self.closed else ""
            return f"<{cs}{self.__class__.__name__} home='{self.home}' {name=}>"
        return super().__repr__()

    def _get_template_controls(self):
        if self.SHOW_TEMPLATE_CONTROLS:
            return self.template_controls
        return None

    def _on_template_controls_expand(self, b: ModalBox):
        if getattr(self, "_n_template_folders", 0) != len(_template_folders):
            self.update_templates()
        self._sw_template.options = self.templates

    @staticmethod
    def register_template_root_folder(folder: pathlib.Path):
        """Register a root folder that contains folders of yaml templates by MenuBoxVT
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

    @classproperty
    def templates(cls) -> dict:  # noqa: N805
        """Templates for the class will be available in this dict mapping a name to
        dict of the settings.

        The settings can be defined as yaml files in the _template_folder.
        """
        if not hasattr(cls, "_templates"):
            cls.update_templates()
        return cls._templates

    @classmethod
    def update_templates(cls):
        cls._templates = {}
        for root in _template_folders:
            folder = root.joinpath(cls.__name__)
            if folder.exists():
                for f in folder.glob("*"):
                    if f.is_file() and f.suffix in [".yaml", ".json"]:
                        cls._templates[f.stem] = f
        cls._n_template_folders = len(_template_folders)

    async def button_clicked(self, b: ipw.Button):
        await super().button_clicked(b)
        match b:
            case self._button_load_template:
                if self._sw_template.value:
                    self.set_trait("value", self._sw_template.value)
                    self.template_controls.collapse()
            case self._button_template_info:
                self._show_template_info()
            case self.button_clip_put:
                self.to_clipboard()
            case self.button_paste:
                self.from_clipboard()
            case self.button_configure:
                self.load_view(self._CONFIGURE_VIEW if self.view != self._CONFIGURE_VIEW else self.view_previous)

    def _convert_description(self, value: str):
        if value:
            value = self.fstr(value)
            parameters = self._description_params | {"description": value}
            if self.view == self._CONFIGURE_VIEW:
                parameters["details_open"] = "open"
            return self.fstr(self.DESCRIPTION_VIEWER_TEMPLATE, parameters=parameters)
        return ""

    def _show_template_info(self):
        if self._sw_template.value:
            path = self._sw_template.value
            if isinstance(path, pathlib.Path):
                with path.open() as f:
                    data = f.read()
                mime_type = "text/json" if path.suffix == "json" else "text/yaml"
                ipylab.app.dialog.show_dialog(title=path.name, body=ipylab.CodeEditor(value=data, mime_type=mime_type))

    def _view_configure_get(self):
        if self.RENAMEABLE:
            return self.button_configure, self.text_name, self._box_edit_description
        return self.button_configure, self._box_edit_description

    def from_clipboard(self):
        from pandas.io.clipboard import clipboard_get  # type: ignore

        self.set_trait("value", load_yaml(clipboard_get()))

    def to_clipboard(self):
        from pandas.io.clipboard import clipboard_set  # type: ignore

        clipboard_set(to_yaml(self.value(), walkstring=True))

    def on_change(self, change: ChangeType):
        super().on_change(change)
        if "text_name" in self._trait_values:  # For text_name
            if change["owner"] is self and change["name"] == "name":
                if self.name and not self.RENAMEABLE:
                    self.text_name.disabled = True
                self.text_name.value = self.name
            elif change["owner"] is self.text_name:
                self.name = self.text_name.value
                with self.ignore_change():
                    self.text_name.value = self.name
        if change["name"] == "visibility" and self.view:
            self.mb_refresh()
