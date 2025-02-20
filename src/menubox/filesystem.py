from __future__ import annotations

import asyncio
import pathlib
import re
from typing import TYPE_CHECKING, ClassVar, override

import psutil
import traitlets
from fsspec import AbstractFileSystem, available_protocols, get_filesystem_class

from menubox import mb_async, utils
from menubox import trait_factory as tf
from menubox.menuboxvt import MenuBoxVT
from menubox.pack import to_dict, to_json_dict
from menubox.trait_types import ChangeType, NameTuple, StrTuple

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ipywidgets import Button


def list_drives() -> list[str]:
    "Get a list of the drives in the current filesystem."
    return [p.mountpoint.strip("\\ ") for p in psutil.disk_partitions()]


class Filesystem(MenuBoxVT):
    """Graphical file selector widget copying the `Panel` based gui defined in fsspec.gui."""

    DEFAULT_LAYOUT: ClassVar = {"flex": "1 0 auto"}
    box_center = None
    _fs = None
    _fs_defaults: ClassVar[dict] = {"auto_mkdir": True}
    prev_protocol = "file"
    prev_kwargs: dict | None = None
    folders_only = traitlets.Bool()
    title_description = traitlets.Unicode()
    filters = StrTuple()
    read_only = traitlets.Bool()
    disabled = traitlets.Bool()
    minimized_children = StrTuple("url")
    protocol = tf.Dropdown(
        description="protocol",
        value="file",
        options=sorted(available_protocols()),
        layout={"width": "200px"},
        style={"description_width": "60px"},
    )
    url = tf.Text(
        description="url",
        continuous_update=False,
        layout={"flex": "1 0 auto", "width": "auto"},
        style={"description_width": "25px"},
    )
    drive = tf.Dropdown(value=None, tooltip="Change drive", layout={"width": "max-content"}).configure(
        dynamic_kwgs={"options": lambda _: list_drives()},
        dlink={
            "source": ("protocol", "value"),
            "target": "layout.visibility",
            "transform": lambda protocol: utils.to_visibility(protocol == "file"),
        },
    )
    sw_main = tf.Select(layout={"width": "auto", "flex": "1 0 auto", "padding": "0px 0px 5px 5px"})
    kw = tf.TextareaValidate(
        value="{}",
        description="kw",
        validate=to_json_dict,
        continuous_update=False,
        layout={"flex": "1 1 0%", "width": "inherit", "height": "inherit"},
        style={"description_width": "60px"},
    )
    button_home = tf.Button(description="🏠")
    button_up = tf.Button(description="↑", tooltip="Navigate up one folder")
    button_update_sw_main = tf.AsyncRunButton(
        cfunc="_button_update_sw_main_async", description="↻", cancel_description="✗", tasktype=mb_async.TaskType.update
    )
    button_add = tf.AsyncRunButton(
        cfunc="button_update_sw_main",
        kw={"create": True},
        description="✚",
        tooltip="Create new file or folder",
        disabled=True,
        link_button=True,
    )
    box_settings = tf.HBox(layout={"flex": "0 0 auto", "flex_flow": "row wrap"}).configure(children=("protocol", "kw"))
    control_widgets = tf.HBox(layout={"flex": "0 0 auto", "flex_flow": "row wrap"}).configure(
        children={
            "dottednames": ("button_home", "button_up", "drive", "url", "button_add", "button_update_sw_main"),
            "mode": "monitor",
        }
    )
    views = traitlets.Dict({"Main": "view_main_get"})
    value_traits = NameTuple(*MenuBoxVT.value_traits, "read_only", "sw_main", "drive", "url", "folders_only", "view")
    value_traits_persist = NameTuple("protocol", "url", "kw")

    def __init__(self, url="", filters: Iterable[str] = (), ignore: Iterable[str] = (), **kwargs):
        """
        Parameters
        ----------
        filters : list(str) (optional)
            File endings to include in the listings. If not included, all files are
            allowed. Does not affect directories.
            If given, the endings will appear as checkboxes in the interface
        ignore : list(str) (optional)
            Regex(s) of file basename patterns to ignore, e.g., "\\." for typical
            hidden files on posix
        """
        if self._vt_init_complete:
            return
        if not url:
            url = self.home._url
        super().__init__(url=utils.joinpaths(url), **kwargs)
        self.filters = filters
        self.ignore = tuple(re.compile(i) for i in ignore)
        self.home_url = self.url.value

    @property
    def storage_options(self):
        """Value of the kwargs box as a dictionary"""
        return to_dict(self.kw.value)

    @property
    def fs(self) -> AbstractFileSystem:
        """Current filesystem instance"""
        if self._fs is None:
            cls = get_filesystem_class(self.protocol.value)
            self._fs = cls(**self._fs_defaults | self.storage_options)
        return self._fs

    @property
    def urlpath(self):
        """URL of currently selected item"""
        return ((self.protocol.value or "") + "://" + self.sw_main.value) if self.sw_main.value else None

    async def mb_configure(self):
        for w in (self.protocol, self.url, self.sw_main, self.kw):
            if w:
                self.dlink((self, "disabled"), (w, "disabled"))
        self.update_widget_locks()
        await super().mb_configure()
        self.button_update_sw_main.start()

    def view_main_get(self):
        if self.read_only:
            self.tooltip = f'Configuration of this filesystem "{self.home}→{self.name}") is disabled.'
            return self.sw_main
        return (self.control_widgets, self.box_settings, self.sw_main)

    @override
    def on_change(self, change: ChangeType):
        super().on_change(change)
        match change["owner"]:
            case self.protocol:
                self._fs = None
                self.sw_main.options = []
                self.url.value = ""
                if self.protocol.value == "file":
                    self.drive.options = list_drives()
            case self.url:
                if not self.read_only:
                    self.button_add.disabled = exists = self.fs.exists(self.url.value)
                    if not exists:
                        return
            case self.drive:
                if self.drive.value:
                    self.url.value = self.drive.value
                    self.drive.value = None
            case self.sw_main:
                if self.sw_main.value is None or self.urlpath is None:
                    return
                if self.fs.isdir(self.urlpath):
                    self.url.value = self.fs._strip_protocol(self.urlpath)  # type: ignore
        if change["owner"] is self:
            match change["name"]:
                case "read_only":
                    self.update_widget_locks()
                    if self.view:
                        self.refresh_view()
                case "view":
                    self.button_update_sw_main.start()
        else:
            match change["owner"]:
                case self.url | self.sw_main if self.view_active:
                    self.button_update_sw_main.start()

    async def button_clicked(self, b: Button):
        if self.read_only:
            return
        await super().button_clicked(b)
        match b:
            case self.button_home:
                self.url.value = self.home_url
                self.sw_main.value = None
            case self.button_up:
                self.url.value = self.fs._parent(self.url.value)

    def update_widget_locks(self):
        for widget in (self.url, self.button_up, self.button_home, self.button_add):
            widget.disabled = self.read_only

    async def _button_update_sw_main_async(self, create=False):
        if self.prev_protocol != self.protocol.value or self.prev_kwargs != self.storage_options:
            self._fs = None  # causes fs to be recreated
            self.prev_protocol = self.protocol.value
            self.prev_kwargs = self.storage_options
        if create and not self.fs.exists(self.url.value):
            root, name = utils.splitname(self.url.value)
            self.fs.mkdirs(root, exist_ok=True)
            if "." in name:
                self.fs.touch(self.url.value)
                self.log.info("Created file %s", self.url.value)
                self.url.value = root
                return
            self.fs.mkdirs(self.url.value, exist_ok=True)
            self.log.info("Created folder %s", self.url.value)
        try:
            items = self.fs.ls(self.url.value, detail=True)
        except (NotADirectoryError, FileNotFoundError):
            if not self.read_only and self.view not in self._RESERVED_VIEWNAMES:
                self.url.value = utils.splitname(self.url.value)[0]
            return
        listing = sorted(items, key=lambda x: x["name"])
        listing = [n for n in listing if not any(i.match(n["name"].rsplit("/", 1)[-1]) for i in self.ignore)]
        folders = {}
        files = {}
        if self.fs.isdir(self.url.value):
            folders["📁 ."] = self.url.value
        for o in listing:
            if o["type"] == "directory":
                folders["📁 " + o["name"].rsplit("/", 1)[-1]] = o["name"]
        if not self.folders_only:
            for o in listing:
                if o["type"] == "file":
                    if self.filters and not any(o["name"].endswith(ext) for ext in self.filters):
                        continue
                    files["📄 " + o["name"].rsplit("/", 1)[-1]] = o["name"]
        url = self.sw_main.value
        with self.ignore_change():
            self.sw_main.options = options = folders | files
            if not url or url not in options.values():
                url = None
            self.sw_main.value = url

    async def get_relative_path(self, title=""):
        "Obtain a relative path using a dialog."

        rp = RelativePath(parent=self)
        try:
            title = title or f"Path relative to repository '{self.name}''"
            result = await rp.show_in_dialog(title)
            if not result["value"]:
                raise asyncio.CancelledError
            return rp.relative_path.value
        finally:
            rp.close()


class RelativePath(Filesystem):
    """A relative filesystem"""

    DEFAULT_BORDER = "solid 1px LightGrey"
    folders_only = traitlets.Bool(False)
    box_settings = tf.HBox(layout={"overflow": "hidden", "flex": "0 0 auto"}).configure(children=("relative_path",))
    relative_path = tf.Text(".", description="Relative path", disabled=True, layout={"flex": "1 0 0%"})
    value_traits = NameTuple(*Filesystem.value_traits, "kw")
    value_traits_persist = NameTuple()
    parent: Filesystem

    def __new__(cls, parent: Filesystem, **kwargs):
        return super().__new__(cls, home=parent.home, parent=parent, **kwargs)

    def __init__(self, parent: Filesystem, **kwargs):
        utils.hide(self.drive)
        super().__init__(parent=parent, **parent.to_dict(), **kwargs)

    @property
    def home_url(self):
        return self.parent.url.value

    @home_url.setter
    def home_url(self, value):
        pass

    async def _button_update_sw_main_async(self, create=False):
        await super()._button_update_sw_main_async(create=create)
        url = pathlib.PurePath(self.sw_main.value or self.url.value)
        base = self.home_url
        try:
            self.relative_path.value = v = utils.joinpaths(url.relative_to(base))
            self.button_up.disabled = v == "."
        except ValueError:
            self.url.value = base
