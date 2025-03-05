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
from menubox.menuboxvt import MenuboxVT
from menubox.pack import to_dict, to_json_dict
from menubox.trait_types import ChangeType, NameTuple, StrTuple

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ipywidgets import Button


def list_drives() -> list[str]:
    "Get a list of the drives in the current filesystem."
    return [p.mountpoint.strip("\\ ") for p in psutil.disk_partitions()]


class Filesystem(MenuboxVT):
    """Graphical file selector widget copying the `Panel` based gui defined in fsspec.gui."""

    box_center = None
    _fs = None
    _fs_defaults: ClassVar[dict] = {"auto_mkdir": True}
    prev_protocol = traitlets.Enum(values=sorted(available_protocols()), default_value="file")
    prev_kwargs = traitlets.Dict()
    folders_only = traitlets.Bool()
    read_only = traitlets.Bool()
    disabled = traitlets.Bool()
    title_description = traitlets.Unicode()
    filters = StrTuple()
    minimized_children = StrTuple("url")
    value_traits = NameTuple(*MenuboxVT.value_traits, "read_only", "sw_main", "drive", "url", "folders_only", "view")
    value_traits_persist = NameTuple("protocol", "url", "kw")
    views = traitlets.Dict({"Main": ()})

    protocol = tf.Dropdown(
        description="protocol",
        value="file",
        options=sorted(available_protocols()),
        layout={"width": "200px"},
        style={"description_width": "60px"},
    )
    url = tf.Combobox(
        description="url",
        # continuous_update=False,
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
    sw_main = tf.Select(
        layout={"width": "auto", "flex": "1 0 auto", "padding": "0px 0px 5px 5px"},
    )
    kw = tf.TextareaValidate(
        value="{}",
        description="kw",
        validate=to_json_dict,
        continuous_update=False,
        layout={"flex": "1 1 0%", "width": "inherit", "height": "inherit"},
        style={"description_width": "60px"},
    )
    button_update = tf.AsyncRunButton(
        cfunc="_button_update_async",
        description="↻",
        cancel_description="✗",
        tasktype=mb_async.TaskType.update,
    )
    button_home = tf.Button_main(
        description="🏠",
    )
    button_up = tf.Button_main(
        description="↑",
        tooltip="Navigate up one folder",
    )
    button_add = tf.Button_main(
        description="✚",
        tooltip="Create new file or folder",
    )
    box_settings = tf.HBox(layout={"flex": "0 0 auto", "flex_flow": "row wrap"}).configure(children=("protocol", "kw"))
    control_widgets = tf.HBox(layout={"flex": "0 0 auto", "flex_flow": "row wrap"}).configure(
        children={
            "dottednames": ("button_home", "button_up", "drive", "url", "button_add", "button_update"),
            "mode": "monitor",
        }
    )

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

    async def init_async(self):
        for w in (self.protocol, self.url, self.sw_main, self.kw):
            if w:
                self.dlink((self, "disabled"), (w, "disabled"))
        self.update_widget_locks()
        await super().init_async()

    @override
    async def get_center(self, view: str | None):
        if view == "Main":
            if self.read_only:
                self.tooltip = f'Configuration of this filesystem "{self.home}→{self.name}") is disabled.'
                return view, self.sw_main
            return view, (self.control_widgets, self.box_settings, self.sw_main)
        return await super().get_center(view)

    @override
    def on_change(self, change: ChangeType):
        super().on_change(change)
        match change["owner"]:
            case self.protocol:
                if self.button_update.task:
                    self.button_update.task.cancel("Protocol change")
                self._fs = None
                self.sw_main.options = []
                self.url.value = ""
                if self.protocol.value == "file" and self.drive:
                    self.drive.options = list_drives()
            case self.drive:
                if drive := self.drive.value:
                    self.drive.value = None
                    self.url.value = drive
        if change["owner"] is self:
            match change["name"]:
                case "read_only":
                    self.update_widget_locks()
                    if self.view:
                        self.refresh_view()
                case "view" if self.view_active:
                    self.button_update.start()
        elif self.view_active:
            match change["owner"]:
                case self.url:
                    self.button_update.start(url=self.url.value)
                case self.sw_main:
                    self.button_update.start(url=self.sw_main.value)

    async def button_clicked(self, b: Button):
        if self.read_only:
            return
        await super().button_clicked(b)
        match b:
            case self.button_home:
                await self.button_update.start_wait(url=self.home_url)
            case self.button_up:
                await self.button_update.start_wait(url=self.fs._parent(self.url.value))
            case self.button_add:
                await self.button_update.start_wait(url=self.url.value, create=True)

    def update_widget_locks(self):
        for widget in (self.url, self.button_up, self.button_home, self.button_add):
            widget.disabled = self.read_only

    async def _button_update_async(self, create=False, url: str | None = None):
        if self.prev_protocol != self.protocol.value or self.prev_kwargs != self.storage_options:
            self._fs = None  # causes fs to be recreated
            self.prev_protocol = self.protocol.value
            self.prev_kwargs = self.storage_options
        if url is None:
            url = self.url.value
        self.button_add.disabled = True
        fs = self.fs
        exists = await mb_async.to_thread(fs.exists, url)
        try:
            if not exists:
                if not create:
                    return
                root, name = utils.splitname(url)
                await mb_async.to_thread(fs.mkdirs, root, exist_ok=True)
                if "." in name:
                    fs.touch(url)
                    self.log.info("Created file %s", url)
                    self.url.value = root
                    return
                await mb_async.to_thread(fs.mkdirs, url, exist_ok=True)
                self.log.info("Created folder %s", url)
                exists = True
            try:
                items = await mb_async.to_thread(fs.ls, url, detail=True)
            except (NotADirectoryError, FileNotFoundError):
                if not self.read_only and self.view not in self._RESERVED_VIEWNAMES:
                    self.url.value = utils.splitname(url)[0]
                return
            listing = sorted(items, key=lambda x: x["name"])
            listing = [n for n in listing if not any(i.match(n["name"].rsplit("/", 1)[-1]) for i in self.ignore)]
            folders = {}
            files = {}
            if await mb_async.to_thread(fs.isdir, url):
                folders["📁 ."] = url
            for o in listing:
                if o["type"] == "directory":
                    folders["📁 " + o["name"].rsplit("/", 1)[-1]] = o["name"]
            if not self.folders_only:
                for o in listing:
                    if o["type"] == "file":
                        if self.filters and not any(o["name"].endswith(ext) for ext in self.filters):
                            continue
                        files["📄 " + o["name"].rsplit("/", 1)[-1]] = o["name"]
            # url = self.sw_main.value
            with self.ignore_change():
                self.sw_main.options = options = folders | files
                self.url.options = options = tuple(options.values())
                self.sw_main.value = url if url in options else None
                self.url.value = url
        except asyncio.CancelledError:
            pass
        finally:
            self.button_add.disabled = exists or self.read_only

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

    folders_only = traitlets.Bool(False)
    box_settings = tf.HBox(layout={"overflow": "hidden", "flex": "0 0 auto"}).configure(children=("relative_path",))
    relative_path = tf.Text(".", description="Relative path", disabled=True, layout={"flex": "1 0 0%"})
    value_traits = NameTuple(*Filesystem.value_traits, "kw")
    value_traits_persist = NameTuple()
    parent: Filesystem

    def __new__(cls, parent: Filesystem, **kwargs):
        return super().__new__(cls, home=parent.home, parent=parent, **kwargs)

    def __init__(self, parent: Filesystem, **kwargs):
        self.disable_widget("drive")
        super().__init__(parent=parent, value=parent.to_dict(), **kwargs)

    @property
    def home_url(self):
        return self.parent.url.value

    @home_url.setter
    def home_url(self, value):
        pass

    async def _button_update_async(self, create=False, url: str | None = None):
        await super()._button_update_async(create=create, url=url)
        url_ = pathlib.PurePath(self.sw_main.value or self.url.value or "")
        base = self.home_url
        try:
            self.relative_path.value = v = utils.joinpaths(url_.relative_to(base))
            self.button_up.disabled = v == "."
        except ValueError:
            self.url.value = base
