from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

import ipywidgets as ipw
import pandas as pd
import traitlets

import menubox.defaults as dv
from menubox import mb_async, utils
from menubox import trait_factory as tf
from menubox.home import Home
from menubox.log import TZ
from menubox.menuboxvt import MenuBoxVT
from menubox.pack import deep_copy, load_yaml
from menubox.trait_types import ChangeType, StrTuple, TypedTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from fsspec import AbstractFileSystem


class MenuBoxPersist(MenuBoxVT):
    """Persistence of nested settings in yaml files plus persistence of dataframes
    in home.repository.

    Settings to be persisted are defined in the name_tuple `value_traits_persist`.
    This tuple may be revised at any time, though it is usual to define this list in the
    class definition. Values in the name tuple should be either traits or objects that
    are defined prior validation of `value_traits_persist`. This occurs at the end of
    init, so  objects.

    If persistence data exists, a task is created to load persistence data after init.

    Multiple versions of persistence data may be possible, if `SINGLE_VERSION`
    is False. Loading of persistence data is possible by selecting the version in the
    version widget.

    Widgets, and other objects with a `value` are considered as the the value to be
    persisted. So for a widget defined as `my_widget` the value of `my_widget` is
    persisted instead of the widget. Using `my_widget.value` is equivalent although
    `my_widget.options` is also possible in which case adding `my_widget` after
    `my_widget.options` is necessary.

    Settings of nested objects are stored in the same settings file by name. For
    ValueTrait objects (including MenuBoxVT), settings defined in `value_traits_persist`
    are the `value` so are stored by default.

    Persistence of DataFrames in `value_traits_persist` is not permitted. The tuple
    `dataframe_persist` is provided to persist dataframes in a folder of the same name
    as the yaml data.
    """

    SINGLETON_BY = ("home", "name")
    _PERSIST_TEMPLATE = "settings/{cls.__name__}/{name}_v{version}"
    _AUTOLOAD = True
    SINGLE_VERSION = True
    SHOW_TEMPLATE_CONTROLS = True
    DEFAULT_VIEW = None
    title_description = traitlets.Unicode(
        "<b>{self.FANCY_NAME or self.__class__.__name__}&emsp;"
        "{self.name.replace('_',' ').capitalize()}"
        "{'' if self.SINGLE_VERSION else f' V{self.version}'}</b>"
    )
    version = traitlets.Int(1, read_only=True)
    versions = TypedTuple(traitlets.Int())
    saved_timestamp = traitlets.Unicode()
    menu_load_index = tf.ModalBox(
        "_get_version_box",
        title="Persistence",
        button_expand_description="⇵",
        button_expand_tooltip="Save / load persistence settings.",
    ).configure(
        allow_none=True,
    )
    sw_version_load = tf.Dropdown(
        description="Load from",
        index=None,
        layout={"width": "max-content"},
    ).configure(
        dlink={"source": ("self", "versions"), "target": "options"},
    )
    button_save_persistence_data = tf.AsyncRunButton(
        cfunc="_button_save_persistence_data_async",
        description="💾",
        tooltip="Save persistence data for current version",
        tasktype=mb_async.TaskType.update,
        **dv.b_kwargs,
    )
    version_widget = tf.BoundedIntText(
        min=1,
        max=1,
        step=1,
        description="Version",
        tooltip="Changing the version will switch to the new version dropping"
        " unsaved changes. \n"
        "If a new version doesn't exist, the present values are retained and can be"
        " saved in the new version.",
        layout={"width": "130px"},
    ).configure(
        dynamic_kwgs={"disabled": "SINGLE_VERSION"},
    )
    box_version = tf.Box()
    header_right_children = StrTuple("menu_load_index", *MenuBoxVT.header_right_children)

    task_loading_persistence_data = tf.Task()
    views = traitlets.Dict({"Main": "view_main_get"})
    value_traits = StrTuple(*MenuBoxVT.value_traits, "version", "sw_version_load")
    value_traits_persist = StrTuple("saved_timestamp", "name", "description")
    dataframe_persist = StrTuple()

    @classmethod
    def validate_name(cls, name: str) -> str:
        return utils.sanatise_filename(name).lower()

    def _update_versions(self) -> None:
        self.versions = self.get_persistence_versions(self.home, self.name, self.log)

    async def init_async(self):
        await super().init_async()
        if self.name and self._AUTOLOAD:
            version = self.get_latest_version()
            if self.versions:
                await self.load_persistence_data(version, set_version=True)
            elif self.menu_load_index:
                self.menu_load_index.expand()
        if not self.SINGLE_VERSION:
            self.add_value_traits("version_widget")

    def on_change(self, change: ChangeType) -> None:
        super().on_change(change)
        if not self._MenuBox_init_complete:
            return
        if not self.SINGLE_VERSION:
            self.version_widget.max = max(self.versions or (0,)) + 1
        if change["owner"] is self and change["name"] in ["name", "version"]:
            if self.name and change["name"] == "name" and self.version > 0:
                with self.ignore_change():
                    self.set_trait("version", 1)
                    self.version_widget.max = 1
            if self._AUTOLOAD and self.version in self.versions:
                self.load_persistence_data(self.version, set_version=True)
        if change["owner"] is self.version_widget:
            self.set_trait("version", self.version_widget.value)
        if change["owner"] is self.sw_version_load and self.sw_version_load.value is not None:
            self.load_persistence_data(self.sw_version_load.value, quiet=False)
            self.sw_version_load.value = None

    def _get_version_box(self) -> ipw.Box:
        box = self.box_version
        self._update_versions()
        if len(self.versions):
            self.sw_version_load.value = None
            box.children = tuple(
                self.get_widgets(
                    self.version_widget,
                    self.button_save_persistence_data,
                    self.sw_version_load,
                    self.button_clip_put,
                    self.button_paste,
                )
            )
        else:
            box.children = [ipw.HTML('<font color="red">Not saved yet!</font>'), self.button_save_persistence_data]
        return box

    async def _button_save_persistence_data_async(self, version=None):
        """Use button_save.start to get an awaitable task."""
        repo = self.home.repository
        version = self._to_version(version)
        path = repo.to_path(self._get_persist_name(self.name, version))
        self.saved_timestamp = str(pd.Timestamp.now(TZ))
        await mb_async.to_thread(self.to_yaml, self.value(), fs=repo.fs, path=path)
        if self.dataframe_persist:
            await self.save_dataframes_async(self.name, version)
        self._update_versions()
        self.log.info(f"Saved persistence data: {path=!s}")
        if self.menu_load_index:
            self.menu_load_index.collapse()
        self.text_name.disabled = True
        return path

    async def save_dataframes_async(self, name: str, version: int) -> None:
        repo = self.home.repository
        for dotted_name in self.dataframe_persist:
            df: pd.DataFrame = utils.getattr_nested(self, dotted_name)
            if df.empty:
                continue
            path = repo.to_path(self.get_df_filename(name, version, dotted_name))
            await mb_async.to_thread(self.save_dataframe, df, repo.fs, path)
            self.log.info(f"Saved {path}")

    async def get_dataframes_async(self, name: str, version: int) -> dict[str, pd.DataFrame]:
        """Obtain a dict mapping the dataframe_persist:df loaded from file."""
        repo = self.home.repository
        values = {}
        for dotted_name in self.dataframe_persist:
            path = repo.to_path(self.get_df_filename(name, version, dotted_name))
            coro = mb_async.to_thread(self.load_dataframe, repo.fs, path)
            try:
                values[dotted_name] = await coro
                self.log.info(f"loaded {path}")
            except FileNotFoundError:
                continue
        return values

    @classmethod
    def _get_persist_name(cls, name: str, version: int | str, extn=".yaml") -> str:
        """Get the path for the persistence file."""

        base = cls.get_persistence_base(name, version)
        return base + extn

    @classmethod
    def get_persistence_base(cls, name: str, version: int | str) -> str:
        if not version or not isinstance(version, str) and version < 1:
            msg = f"version must be >= 1 but is {version}"
            raise ValueError(msg)
        return utils.fstr(cls._PERSIST_TEMPLATE, cls=cls, name=name, version=version).lower()

    @classmethod
    def list_stored_datasets(cls, home: Home | str) -> list[str]:
        """List the stored datasets for this class."""
        repo = Home(home).repository
        datasets = set()
        ptn = repo.to_path(cls._get_persist_name("*", "*"))
        for f in repo.fs.glob(str(ptn)):
            datasets.add(utils.stem(f).rsplit("_v", maxsplit=1)[0])  # type: ignore
        return sorted(datasets)

    @classmethod
    def get_df_filename(cls, name: str, version: int, dotted_name: str) -> str:
        base = cls.get_persistence_base(name, version)
        return pathlib.Path(base, utils.sanatise_filename(f"{dotted_name}.parquet")).as_posix()

    @classmethod
    def get_persistence_versions(cls, home: Home | str, name: str, log=None) -> tuple[int, ...]:
        repo = Home(home).repository
        path = repo.to_path(cls._get_persist_name(name, "*"))
        files = repo.fs.glob(str(path))
        versions = set()
        for f in files:
            try:
                versions.add(int(pathlib.PurePath(f).stem.split("v")[-1]))  # type: ignore
            except Exception:
                if log:
                    log.warning(f"This file is missing a valid version {f}")
        try:
            if cls.SINGLE_VERSION:
                if 1 in versions:
                    return (1,)
                return ()
            return tuple(sorted(versions))
        except Exception:
            return ()

    async def load_view_async(self, view: str | None):
        if not self.name:
            view = self._CONFIGURE_VIEW
        return await super().load_view_async(view)

    @mb_async.singular_task(tasktype=mb_async.TaskType.update, handle="task_loading_persistence_data")
    async def load_persistence_data(self, version=None, quiet=False, data: dict | None = None, set_version=False):
        """Loads persistence data from file.

        (loading data is async)
        """
        if data is None:
            try:
                version = self._to_version(version)
                data = await mb_async.to_thread(
                    self.get_persistence_data, self.home, self.name, self._to_version(version)
                )
                if self.dataframe_persist:
                    df_data = await self.get_dataframes_async(self.name, version)
                    data = df_data | data
            except FileNotFoundError:
                if quiet:
                    return
            except Exception:
                raise
        if data:
            self.set_trait("value", data)
        if version is not None and set_version:
            with self.ignore_change():
                self.set_trait("version", version)
                self.version_widget.max = version + 1
                self.version_widget.value = version
                self.sw_version_load.value = None
        if self.menu_load_index:
            self.menu_load_index.collapse()
        self.update_title()

    @classmethod
    def get_persistence_data(cls, home: str | Home, name: str, version: int | None = None) -> dict:
        repo = Home(home).repository
        versions = cls.get_persistence_versions(home, name)
        if not versions or version is not None and version not in versions:
            return {}
        if version is None:
            version = max(versions)
        fname = repo.to_path(cls._get_persist_name(name, version))
        if repo.fs.isfile(fname):
            with repo.fs.open(str(fname)) as file:
                data = load_yaml(file)
                if isinstance(data, dict):
                    return data
                if data:
                    msg = f"Expect dict but got {data}"
                    raise TypeError(msg)
                return {}
        else:
            msg = f"{fname!s} in {repo=}"
            raise FileNotFoundError(msg)

    def get_latest_version(self) -> int:
        self._update_versions()
        return max(self.versions) if self.versions else 1

    def _to_version(self, version: int | None) -> int:
        if version is None:
            version = self.version
        if version < 0:
            version = self.get_latest_version()
        return version

    @classmethod
    def save_dataframe(cls, df: pd.DataFrame, fs: AbstractFileSystem, path: str):
        accessed = False  # Allow for removal of partially written files
        try:
            with fs.open(path, "wb") as f:
                accessed = True
                match path.rsplit(".", maxsplit=1)[-1]:
                    case "csv" | "txt":
                        df.to_csv(f, encoding="utf-8-sig")
                    case "parquet":
                        if df.attrs:
                            df = df.copy()
                            df.attrs = deep_copy(df.attrs, unknown_to_str=True)
                        df.to_parquet(f)  # type: ignore
                    case suffix:
                        raise NotImplementedError(suffix)  # noqa: TRY301
        except Exception:
            if accessed:
                fs.rm_file(path)

    @classmethod
    def load_dataframe(cls, fs: AbstractFileSystem, path: str) -> pd.DataFrame:
        with fs.open(path, "rb") as f:
            match path.rsplit(".", maxsplit=1)[-1]:
                case "csv" | "txt":
                    return pd.read_csv(f, encoding="utf-8-sig")
                case "parquet":
                    return pd.read_parquet(f)  # type: ignore
                case suffix:
                    raise NotImplementedError(suffix)

    def view_main_get(self) -> ipw.Widget | Iterable[ipw.Widget | str | Callable] | Callable:
        return ipw.HTML(f"This function should be overloaded: {utils.fullname(self.view_main_get)}")
