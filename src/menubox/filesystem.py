from __future__ import annotations

import asyncio
import pathlib
import re
from typing import TYPE_CHECKING, ClassVar, Self, cast, override

import psutil
from fsspec import AbstractFileSystem, available_protocols, get_filesystem_class

from menubox import defaults, mb_async, utils
from menubox import trait_factory as tf
from menubox.hashome import HasHome, Home
from menubox.menuboxvt import MenuboxVT
from menubox.pack import to_dict, to_json_dict
from menubox.trait_types import ChangeType, NameTuple, StrTuple

if TYPE_CHECKING:
    from ipywidgets import Button


def list_drives() -> list[str]:
    "Get a list of the drives in the current filesystem."
    return [p.mountpoint.strip("\\ ") for p in psutil.disk_partitions()]


class Filesystem(MenuboxVT):
    """Graphical file selector widget copying the `Panel` based gui defined in fsspec.gui."""

    box_center = None
    _fs = None
    _ignore = ()
    startup_dir = utils.joinpaths(pathlib.Path().cwd())
    _fs_defaults: ClassVar[dict] = {"auto_mkdir": True}
    prev_protocol = tf.Str(default=lambda _: "file")
    prev_kwargs = tf.Dict()
    folders_only = tf.Bool()
    read_only = tf.Bool()
    title_description = tf.Str()
    home_url = tf.Str()
    filters = StrTuple()
    ignore = StrTuple()
    minimized_children = StrTuple("url")
    value_traits = NameTuple(*MenuboxVT.value_traits, "read_only", "sw_main", "drive", "view")
    value_traits_persist = NameTuple("protocol", "url", "kw", "folders_only", "filters", "ignore")
    views = tf.ViewDict(default=lambda _: {"Main": ()})

    protocol = tf.Dropdown(
        cast(Self, 0),
        description="protocol",
        value="file",
        options=sorted(available_protocols()),
        layout={"width": "200px"},
        style={"description_width": "60px"},
    ).hooks(
        on_set=lambda c: c["parent"].dlink(source=(c["parent"], "read_only"), target=(c["obj"], "disabled")),
    )
    url = tf.Combobox(
        description="url",
        # continuous_update=False,
        layout={"flex": "1 0 auto", "width": "auto"},
        style={"description_width": "25px"},
    ).hooks(
        on_set=lambda c: c["parent"].dlink(source=(c["parent"], "read_only"), target=(c["obj"], "disabled")),
    )
    drive = tf.Dropdown(
        cast(Self, 0),
        value=None,
        tooltip="Change drive",
        layout={"width": "max-content"},
        options=list_drives(),
    ).hooks(
        on_set=lambda c: (
            c["parent"].dlink(
                source=(c["parent"].protocol, "value"),
                target=(c["obj"].layout, "visibility"),
                transform=lambda protocol: utils.to_visibility(protocol == "file"),
            ),
            c["parent"].dlink(source=(c["parent"], "read_only"), target=(c["obj"], "disabled")),
        )
    )
    kw = tf.TextareaValidate(
        value="{}",
        description="kw",
        validate=to_json_dict,
        continuous_update=False,
        layout={"flex": "1 1 0%", "width": "inherit", "height": "inherit"},
        style={"description_width": "60px"},
    ).hooks(
        on_set=lambda c: c["parent"].dlink(source=(c["parent"], "read_only"), target=(c["obj"], "disabled")),
    )
    sw_main = tf.Select(
        layout={"width": "auto", "flex": "1 0 auto", "padding": "0px 0px 5px 5px"},
    )
    button_update = tf.AsyncRunButton(
        cast(Self, 0),
        cfunc=lambda p: p._button_update_async,
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
    box_settings = tf.HBox(cast(Self, 0), layout={"flex": "0 0 auto", "flex_flow": "row wrap"}).hooks(
        set_children=lambda p: (p.protocol, p.kw),
    )
    control_widgets = tf.HBox(layout={"flex": "0 0 auto", "flex_flow": "row wrap"}).hooks(
        set_children={
            "dottednames": ("button_home", "button_up", "drive", "url", "button_add", "button_update"),
            "mode": "monitor",
        }
    )

    @property
    def root(self):
        return self.url.value

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

    @override
    async def init_async(self):
        await super().init_async()
        if self.protocol.value == "file" and not self.root:
            self.url.value = self.startup_dir
        self.home_url = self.root

    @override
    def load_value(self, data):
        if data is not defaults.NO_VALUE and data:
            self.button_update.cancel(message="loading data into filesystem")
            super().load_value(data)
            self.home_url = self.root
            self.button_update.start()

    @override
    async def get_center(self, view: str | None):
        if view == "Main":
            if self.read_only:
                self.tooltip = "This filesystem ({self.name}) is read only."
                return view, self.sw_main
            return view, (self.control_widgets, self.box_settings, self.sw_main)
        return await super().get_center(view)

    @override
    def on_change(self, change: ChangeType):
        super().on_change(change)
        if self.read_only:
            return
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
                case "view" if self.view_active:
                    self.button_update.start()
                case "ignore":
                    self._ignore = tuple(re.compile(i) for i in self.ignore)
        elif self.view_active:
            match change["owner"]:
                case self.url:
                    self.button_update.start()
                case self.sw_main:
                    self.button_update.start(url=self.sw_main.value)

    @override
    async def button_clicked(self, b: Button):
        if self.read_only:
            return
        await super().button_clicked(b)
        match b:
            case self.button_home:
                await self.button_update.start_wait(url=self.home_url)
            case self.button_up:
                await self.button_update.start_wait(url=self.fs._parent(self.root))
            case self.button_add:
                await self.button_update.start_wait(url=self.root, create=True)

    async def _button_update_async(self, create=False, url: str | None = None):
        if (not self.view_active and not create) or self.vt_validating:
            return
        if self.prev_protocol != self.protocol.value or self.prev_kwargs != self.storage_options:
            self._fs = None  # causes fs to be recreated
            self.set_trait("prev_protocol", self.protocol.value)
            self.prev_kwargs = self.storage_options
        if url is None:
            url = self.root
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
                    await self._button_update_async(url=root)
                    return
                await mb_async.to_thread(fs.mkdirs, url, exist_ok=True)
                self.log.info("Created folder %s", url)
                exists = True
            try:
                items = await mb_async.to_thread(fs.ls, url, detail=True)
            except (NotADirectoryError, FileNotFoundError):
                if not self.read_only and self.view not in self.RESERVED_VIEWNAMES:
                    await self._button_update_async(url=utils.splitname(url)[0])
                return
            listing = sorted(items, key=lambda x: x["name"])
            listing = [n for n in listing if not any(i.match(n["name"].rsplit("/", 1)[-1]) for i in self._ignore)]
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
            title = title or f"Path relative to filesystem '{self.name}''"
            result = await rp.show_in_dialog(title)
            if not result["value"]:
                raise asyncio.CancelledError
            return rp.relative_path.value
        finally:
            rp.close()

    async def write(self, path: str, data: bytes):
        "Write the file at path inside a thread"
        await mb_async.to_thread(self._write, path, data)

    def _write(self, path: str, data: bytes):
        with self.fs.open(path, "wb") as f:
            f.write(data)  # type: ignore

    def to_path(self, *parts: str):
        """Will join the parts. If a local file system, it will return an absolute path.

        Returns:
            str: posix style.
        """
        if self.protocol.value == "file":
            return utils.joinpaths(self.root, *parts)
        return utils.joinpaths(self.root, *parts)


class RelativePath(Filesystem):
    """A relative filesystem"""

    folders_only = tf.Bool(default=lambda _: False)
    box_settings = tf.HBox(cast(Self, 0), layout={"overflow": "hidden", "flex": "0 0 auto"}).hooks(
        set_children=lambda p: (p.relative_path,)
    )
    relative_path = tf.Text(value=".", description="Relative path", disabled=True, layout={"flex": "1 0 0%"})
    value_traits = NameTuple(*Filesystem.value_traits, "kw")
    value_traits_persist = NameTuple()
    parent: Filesystem

    def __new__(cls, parent: Filesystem, **kwargs) -> Self:
        return super().__new__(cls, parent=parent, **kwargs)

    def __init__(self, parent: Filesystem, **kwargs):
        self.disable_ihp("drive")
        super().__init__(parent=parent, value=parent.to_dict(), **kwargs)

    @property
    def home_url(self):
        return self.parent.url.value

    @home_url.setter
    def home_url(self, value):
        pass

    @override
    async def _button_update_async(self, create=False, url: str | None = None):
        await super()._button_update_async(create=create, url=url)
        url_ = pathlib.PurePath(self.sw_main.value or self.root)
        base = self.home_url
        try:
            self.relative_path.value = v = utils.joinpaths(url_.relative_to(base))
            self.button_up.disabled = v == "."
        except ValueError:
            self.url.value = base
            if await mb_async.to_thread(self.fs.exists, base):
                await self._button_update_async(url=base)


class DefaultFilesystem(HasHome, Filesystem):
    SINGLE_BY = ("home",)
    KEEP_ALIVE = True
    name = tf.InstanceHP(cast(Self, 0), klass=str, default=lambda c: f"{c['parent'].home}")
    read_only = tf.Bool(default=lambda _: True).configure(allow_none=False, read_only=True)
    parent = None

    @override
    def __init__(self, *, home: Home):
        super().__init__()


class HasFilesystem(HasHome):
    filesystem = (
        tf.InstanceHP(cast(Self, 0), klass=Filesystem, default=lambda c: DefaultFilesystem(home=c["parent"].home))
        .configure(allow_none=False, read_only=False)
        .hooks(on_replace_close=False, set_parent=False)
    )

    def __new__(cls, *, home=None, parent=None, filesystem: Filesystem | None = None, **kwargs):
        if not filesystem:
            if isinstance(parent, HasFilesystem):
                filesystem = parent.filesystem
            else:
                home = cls.to_home(home, parent)
                filesystem = home.filesystem
        inst = super().__new__(cls, home=home, parent=parent, filesystem=filesystem, **kwargs)
        inst.filesystem = filesystem
        return inst
