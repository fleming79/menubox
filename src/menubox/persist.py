from __future__ import annotations

import asyncio
import enum
from typing import TYPE_CHECKING, ClassVar, Generic, Self, cast, final, override

import ipywidgets as ipw
import pandas as pd
import traitlets

import menubox
from menubox import mb_async, utils
from menubox import trait_factory as tf
from menubox.filesystem import HasFilesystem
from menubox.instance import IHPCreate
from menubox.instancehp_tuple import InstanceHPTuple
from menubox.log import TZ
from menubox.menuboxvt import MenuboxVT
from menubox.pack import deep_copy, load_yaml
from menubox.trait_types import MP, ChangeType, S, StrTuple, TypedTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable

    from fsspec import AbstractFileSystem

    from menubox.filesystem import Filesystem


class MenuboxPersistMode(enum.Enum):
    """Enumerates the different persistence modes for Menubox data.
    This enum defines how Menubox data is stored and retrieved,
    allowing for different levels of granularity in the persistence path.
    The persistence mode determines the structure of the base path used
    for storing Menubox data, incorporating classname, name, and version
    information as needed.

    Attributes:
        by_classname: Persistence based solely on the classname.
        by_classname_name: Persistence based on classname and name.
        by_classname_version: Persistence based on classname and version.
        by_classname_name_version: Persistence based on classname, name, and version.
    """

    by_classname = enum.auto()
    by_classname_name = enum.auto()
    by_classname_version = enum.auto()
    by_classname_name_version = enum.auto()

    @classmethod
    def create_base_path(cls, mode: MenuboxPersistMode, classname: str, root: str, name: str, version: int | str):
        """Create a base path string based on the specified persistence mode.

        The base path is used as the root directory for storing data.
        The structure of the path depends on the selected persistence mode,
        incorporating the class name, name, and version as needed.

        Args:
            mode: The persistence mode to use.
            classname: The name of the class.
            root: The root directory for all data.
            name: The name of the data.
            version: The version of the data. Must be >= 1 if used in the mode.

        Returns:
            A string representing the base path.

        Raises:
            ValueError: If the version is less than 1 when required by the mode.
            NotImplementedError: If an unsupported persistence mode is provided.
        """
        match mode:
            case MenuboxPersistMode.by_classname:
                return f"{root}/{classname}".lower()
            case MenuboxPersistMode.by_classname_name:
                return f"{root}/{classname}/{name}".lower()
            case MenuboxPersistMode.by_classname_version:
                if isinstance(version, int) and version < 1:
                    msg = f"version must be >= 1 but is {version}"
                    raise ValueError(msg)
                return f"{root}/{classname}_v{version}".lower()
            case MenuboxPersistMode.by_classname_name_version:
                if isinstance(version, int) and version < 1:
                    msg = f"version must be >= 1 but is {version}"
                    raise ValueError(msg)
                return f"{root}/{classname}/{name}_v{version}".lower()
            case _:
                raise NotImplementedError


class MenuboxPersist(HasFilesystem, MenuboxVT, Generic[S]):
    """Persistence of nested settings in yaml files plus persistence of dataframes using
    filesystem.

    Settings to be persisted are defined in the name_tuple `value_traits_persist`.
    This tuple may be revised at any time, though it is usual to define this list in the
    class definition. Values in the name tuple should be either traits or objects that
    are defined prior validation of `value_traits_persist`. This occurs at the end of
    init, so  objects.

    If persistence data exists, a task is created to load persistence data after init.

    Multiple versions of persistence data may be possible, if `PERSIST_MODE`
    is False. Loading of persistence data is possible by selecting the version in the
    version widget.

    Widgets, and other objects with a `value` are considered as the the value to be
    persisted. So for a widget defined as `my_widget` the value of `my_widget` is
    persisted instead of the widget. Using `my_widget.value` is equivalent although
    `my_widget.options` is also possible in which case adding `my_widget` after
    `my_widget.options` is necessary.

    Settings of nested objects are stored in the same settings file by name. For
    ValueTrait objects (including MenuboxVT), settings defined in `value_traits_persist`
    are the `value` so are stored by default.

    Persistence of DataFrames in `value_traits_persist` is not permitted. The tuple
    `dataframe_persist` is provided to persist dataframes in a folder of the same name
    as the yaml data.
    """

    SINGLE_BY = ("filesystem", "name")
    PERSIST_FOLDERNAME = "settings"
    _extn = ".yaml"

    AUTOLOAD = True
    PERSIST_MODE: ClassVar = cast(MenuboxPersistMode, MenuboxPersistMode.by_classname_name)
    SHOW_TEMPLATE_CONTROLS = True
    DEFAULT_VIEW = None
    _mbp_async_init_complete = False

    title_description = traitlets.Unicode(
        "<b>{self.FANCY_NAME or self.__class__.__qualname__}&emsp;"
        "{self.name.replace('_',' ').capitalize()}"
        "{'' if self.PERSIST_MODE.value < MenuboxPersistMode.by_classname_version.value else f' V{self.version}'}</b>"
    )
    version = traitlets.Int(1, read_only=True)
    versions = TypedTuple(traitlets.Int())
    saved_timestamp = traitlets.Unicode()
    menu_load_index = tf.Modalbox(
        cast(Self, None),
        obj=lambda p: p._get_version_box(),
        title="Persistence",
        button_expand_description="⇵",
        button_expand_tooltip="Save / load persistence settings.",
    ).configure(
        allow_none=True,
    )
    sw_version_load = tf.Dropdown(
        cast(Self, None),
        description="Load from",
        index=None,
        layout={"width": "max-content"},
    ).hooks(
        on_set=lambda c: c["parent"].dlink(
            source=(c["parent"], "versions"),
            target=(c["obj"], "options"),
        ),
    )
    button_save_persistence_data = tf.AsyncRunButton(
        cast(Self, None),
        cfunc=lambda p: p._button_save_persistence_data_async,
        description="💾",
        tooltip="Save persistence data for current version",
        tasktype=mb_async.TaskType.update,
    )
    version_widget = (
        tf.InstanceHP(
            cast(Self, None),
            klass=ipw.BoundedIntText,
            default=lambda c: ipw.BoundedIntText(
                min=1,
                max=1,
                step=1,
                description="Version",
                tooltip="Changing the version will switch to the new version dropping unsaved changes. \n"
                "If a new version doesn't exist, the present values are retained and can be saved in the new version.",
                layout={"width": "130px"},
                disabled=c["parent"].PERSIST_MODE.value < MenuboxPersistMode.by_classname_version.value,
            ),
        )
        .hooks(
            on_set=lambda c: (
                c["parent"].dlink(
                    source=(c["parent"], "versions"),
                    target=(c["obj"], "max"),
                    transform=lambda versions: 1
                    if c["parent"].PERSIST_MODE.value < MenuboxPersistMode.by_classname_version.value
                    else max(versions or (0,)) + 1,
                ),
            )
        )
        .configure(allow_none=True)
    )
    box_version = tf.Box()
    header_right_children = StrTuple("menu_load_index", *MenuboxVT.header_right_children)
    task_loading_persistence_data = tf.Task()
    value_traits = StrTuple(*MenuboxVT.value_traits, "version", "sw_version_load", "version_widget")
    value_traits_persist = StrTuple("saved_timestamp", "description")
    dataframe_persist = StrTuple()

    @classmethod
    def validate_name(cls, name: str) -> str:
        return utils.sanatise_filename(name).lower()

    async def _update_versions(self) -> None:
        self.versions = await self.get_persistence_versions(self.filesystem, self.name)

    @override
    async def init_async(self):
        try:
            await super().init_async()
            if self.PERSIST_MODE.value < MenuboxPersistMode.by_classname_version.value:
                self.set_trait("version_widget", None)
                self.drop_value_traits("version_widget")
            if self.name or self.PERSIST_MODE in [
                MenuboxPersistMode.by_classname,
                MenuboxPersistMode.by_classname_version,
            ]:
                await self._update_versions()
                if self.versions:
                    await asyncio.shield(self.load_persistence_data(version=max(self.versions)))
                elif self.menu_load_index:
                    self.menu_load_index.expand()
        finally:
            self._mbp_async_init_complete = True

    @override
    def on_change(self, change: ChangeType) -> None:
        super().on_change(change)
        if not self._mbp_async_init_complete or not self.name:
            return
        if change["owner"] is self:
            if self.AUTOLOAD and change["name"] in ["name", "version"] and self.version in self.versions:
                self.load_persistence_data(self.version, set_version=True)
        else:
            match change["owner"]:
                case self.sw_version_load if (version := self.sw_version_load.value) in self.versions:
                    self.load_persistence_data(version, quiet=False)
                case self.version_widget if self.version_widget and (version := self.version_widget.value):
                    self.load_persistence_data(version, set_version=True)
                    self.sw_version_load.value = None

    def _get_version_box(self) -> ipw.Box:
        box = self.box_version
        mb_async.run_async_singular(self._update_versions(), obj=self)
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

    async def _button_save_persistence_data_async(self, version: int | None = None):
        """Use button_save.start to get an awaitable task."""
        version = await self._to_version(version)
        path = self.filesystem.to_path(self._get_persist_name(self.name, version))
        self.saved_timestamp = str(pd.Timestamp.now(TZ))
        await mb_async.to_thread(self.to_yaml, self.value(), fs=self.filesystem.fs, path=path)
        if self.dataframe_persist:
            await self.save_dataframes_async(self.name, version)
        await self._update_versions()
        self.log.info(f"Saved persistence data: {path=!s}")
        if self.menu_load_index:
            self.menu_load_index.collapse()
        self.text_name.disabled = True
        return path

    async def save_dataframes_async(self, name: str, version: int = 1) -> None:
        """Asynchronously saves dataframes to the filesystem.

        Iterates through the dataframes specified in `self.dataframe_persist`,
        skipping empty dataframes.  Constructs a file path for each dataframe
        based on the given name, version, and dotted name, then saves the
        dataframe to the filesystem using an asynchronous thread.

        Args:
            name (str): The name associated with the dataframes to be saved.
            version (int): The version number associated with the dataframes.
        """
        for dotted_name in self.dataframe_persist:
            df: pd.DataFrame = utils.getattr_nested(self, dotted_name)
            if df.empty:
                continue
            path = self.filesystem.to_path(self.get_df_filename(name, version, dotted_name))
            await mb_async.to_thread(self.save_dataframe, df, self.filesystem.fs, path)
            self.log.info(f"Saved {path}")

    @classmethod
    async def get_dataframes_async(
        cls, filesystem: Filesystem, *, dotted_names: tuple[str, ...], name: str = "", version: int = 1
    ) -> dict[str, pd.DataFrame]:
        """Asynchronously retrieves a dictionary of pandas DataFrames.

        Args:
            name (str): The name associated with the DataFrames.
            version (int): The version number associated with the DataFrames.

        Returns:
            dict[str, pd.DataFrame]: A dictionary where keys are dotted names
            and values are the corresponding pandas DataFrames.  Returns an
            empty dictionary if no DataFrames are found.
        """
        values = {}
        for dotted_name in dotted_names:
            path = filesystem.to_path(cls.get_df_filename(name, version, dotted_name))
            coro = mb_async.to_thread(cls.load_dataframe, filesystem.fs, path)
            try:
                values[dotted_name] = await coro
            except FileNotFoundError:
                continue
        return values

    @classmethod
    def _get_persist_name(cls, name: str = "*", version: int | str = "*") -> str:
        """Get the path for the persistence file."""

        return cls.get_persistence_base(name, version) + cls._extn

    @classmethod
    def get_persistence_base(cls, name: str = "*", version: int | str = "*") -> str:
        return MenuboxPersistMode.create_base_path(
            mode=cls.PERSIST_MODE,
            classname=cls.__name__,
            root=cls.PERSIST_FOLDERNAME,
            name=name,
            version=version,
        )

    @classmethod
    async def list_stored_datasets(cls, filesystem: Filesystem) -> list[str]:
        """List the names of all stored datasets in the given filesystem.

        The names are sorted alphabetically.

        Args:
            filesystem: The the filesystem to search.

        Returns:
            A list of dataset names.
        """
        datasets = set()
        ptn = filesystem.to_path(cls._get_persist_name("*", "*"))
        for f in await mb_async.to_thread(filesystem.fs.glob, ptn):
            datasets.add(utils.stem(f).rsplit("_v", maxsplit=1)[0])  # type: ignore
        return sorted(datasets)

    @classmethod
    def get_df_filename(cls, name: str, version: int, dotted_name: str) -> str:
        """Generates the filename for a DataFrame to be persisted."""
        base = cls.get_persistence_base(name, version)
        return utils.joinpaths(base, f"{dotted_name}.parquet")

    @classmethod
    async def get_persistence_versions(cls, filesystem: Filesystem, name: str = "") -> tuple[int, ...]:
        """Get all persistence versions for a given name."""
        ptn = cls._get_persist_name(name, version="[1-9]*")
        path = filesystem.to_path(ptn)
        files: list[str] = await mb_async.to_thread(filesystem.fs.glob, path)  # type: ignore
        if cls.PERSIST_MODE.value < MenuboxPersistMode.by_classname_version.value:
            return (1,) if files else ()
        versions = set()
        base_ = utils.stem(ptn).rsplit("v", maxsplit=1)[0]
        for f in files:
            base, v = utils.stem(f).rsplit("v", maxsplit=1)
            if base_ != base:
                continue
            versions.add(int(v.removesuffix(cls._extn)))  # type: ignore
        return tuple(sorted(versions))

    @override
    async def get_center(self, view: str | None):
        if not self.name:
            view = self.CONFIGURE_VIEW
        return await super().get_center(view)

    @mb_async.singular_task(tasktype=mb_async.TaskType.update, handle="task_loading_persistence_data")
    async def load_persistence_data(self, version=None, quiet=False, data: dict | None = None, set_version=False):
        """Asynchronously loads persistence data for the menubox.

        This method retrieves and sets the menubox's data from persistent storage.
        It handles loading both regular data and dataframe data, if applicable.
        Args:
            version (int, optional): The version of the data to load. If None, the latest version is loaded. Defaults to None.
            quiet (bool, optional): If True, suppresses FileNotFoundError exceptions. Defaults to False.
            data (dict | None, optional):  A dictionary containing the data to load. If provided, data is loaded from this dictionary instead of disk. Defaults to None.
            set_version (bool, optional): If True, updates the version widget and trait with the loaded version. Defaults to False.
        Raises:
            Exception: If an error occurs during data loading (excluding FileNotFoundError when quiet=True).
        Returns:
            None
        Notes:
            - If `data` is provided, the method bypasses loading from disk and directly sets the menubox's value.
            - If `dataframe_persist` is True, it also loads dataframe data and merges it with the regular data.
            - If `set_version` is True, it updates the version widget to reflect the loaded version.
            - If `menu_load_index` is set, it collapses the menu after loading.
            - Finally, it calls `update_title` to refresh the menubox's title.
        """

        if data is None:
            try:
                version = await self._to_version(version)
                data = await self.get_persistence_data(self.filesystem, self.name, version)
                if df_names := self.dataframe_persist:
                    df_data = await self.get_dataframes_async(
                        self.filesystem,
                        dotted_names=df_names,
                        name=self.name,
                        version=version,
                    )
                    data = df_data | data
            except FileNotFoundError:
                if quiet:
                    return
            except Exception:
                raise
        if data:
            self.set_trait("value", data)
        if version is not None and set_version:
            self.set_trait("version", version)
            with self.ignore_change():
                if self.version_widget:
                    self.version_widget.value = version
                self.sw_version_load.value = None
        if self.menu_load_index:
            self.menu_load_index.collapse()
        self.update_title()

    @classmethod
    async def get_persistence_data(cls, filesystem: Filesystem, name: str = "", version: int | None = None) -> dict:
        """Retrieves persistence data for a given name and version using the filesystem."""
        versions = await cls.get_persistence_versions(filesystem, name)
        if not versions or version is not None and version not in versions:
            return {}
        if version is None:
            version = max(versions)
        fname = filesystem.to_path(cls._get_persist_name(name, version))
        content = await mb_async.to_thread(filesystem.fs.cat_file, fname)
        data = load_yaml(content)
        if isinstance(data, dict):
            return data
        if data:
            msg = f"Expect dict but got {type(data)} for {fname=}"
            raise TypeError(msg)
        return {}

    async def get_latest_version(self) -> int:
        """Retrieves the latest version number from the available versions.

        If no versions are available, it returns a default version number of 1.

        Returns:
            int: The latest version number, or 1 if no versions are available.
        """
        await self._update_versions()
        return max(self.versions) if self.versions else 1

    async def _to_version(self, version: int | None) -> int:
        if version is None:
            version = self.version
        if version < 0:
            version = await self.get_latest_version()
        return version

    @classmethod
    def save_dataframe(cls, df: pd.DataFrame, fs: AbstractFileSystem, path: str):
        """Save a Pandas DataFrame to a file using the given filesystem.

        Args:
            df: The Pandas DataFrame to save.
            fs: The filesystem to use for saving.
            path: The path to save the DataFrame to. The suffix of the path
            determines the file format. Supported formats are:
            - csv, txt: CSV file
            - parquet: Parquet file

        Raises:
            NotImplementedError: If the file suffix is not supported.
        """
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
        """Load a dataframe from the given path on the given filesystem.

        Args:
            fs: The filesystem to load from.
            path: The path to load from.

        Returns:
            The loaded dataframe.

        Raises:
            NotImplementedError: If the file extension is not supported.
        """
        with fs.open(path, "rb") as f:
            match path.rsplit(".", maxsplit=1)[-1]:
                case "csv" | "txt":
                    return pd.read_csv(f, encoding="utf-8-sig")
                case "parquet":
                    return pd.read_parquet(f)  # type: ignore
                case suffix:
                    raise NotImplementedError(suffix)


@final
class MenuboxPersistPool(HasFilesystem, MenuboxVT, Generic[S, MP]):
    """A Menubox that can load MenuboxPersist instances into the shell."""

    SINGLE_BY = ("klass", "filesystem")
    RENAMEABLE = False
    pool = InstanceHPTuple[Self, MP](
        trait=traitlets.Instance(MenuboxPersist),
        factory=lambda c: c["parent"].factory_pool(**c["kwgs"]),
    ).hooks(
        update_item_names=("name", "versions"),
        set_parent=True,
        close_on_remove=False,
    )
    obj_name = tf.Combobox(cast(Self, None), placeholder="Enter name or select existing", continuous_update=True).hooks(
        on_set=lambda c: (
            c["parent"].update_names(),
            c["parent"].dlink(source=(c["parent"], "names"), target=(c["obj"], "options")),
        )
    )
    names = menubox.StrTuple()
    title_description = traitlets.Unicode("<b>{self.klass.__qualname__.replace('_','').capitalize()} set</b>")
    html_info = tf.HTML()
    info_html_title = ipw.HTML(layout={"margin": "0px 20px 0px 40px"})
    button_update_names = tf.Button_main(description="↻", tooltip="Update options")
    box_main = tf.HBox(cast(Self, None)).hooks(set_children=lambda p: (p.obj_name, p.button_update_names))
    box_center = None
    views = traitlets.Dict({"Main": "box_main"})

    @override
    @classmethod
    def get_single_key(cls, name="default", **kwgs) -> Hashable:
        return super().get_single_key(name=name, **kwgs)

    def factory_pool(self, **kwgs):
        kwgs["filesystem"] = self.filesystem
        if self._factory:
            return self._factory(IHPCreate(name="", parent=self, kwgs=kwgs, klass=self.klass))
        return self.klass(**kwgs)

    @mb_async.debounce(0.01)
    async def update_names(self) -> list[str]:
        """List the stored datasets for the klass."""
        names = await self.klass.list_stored_datasets(self.filesystem)
        self.set_trait("names", names)
        return names

    def __init__(self, *, klass: type[MP], factory: Callable[[IHPCreate], MP] | None = None, **kwgs):
        if self._HasParent_init_complete:
            return
        self.klass = klass
        self._factory = factory
        super().__init__(**kwgs)

    @override
    async def button_clicked(self, b: ipw.Button):
        await super().button_clicked(b)
        match b:
            case self.button_update_names:
                self.update_names()

    def get_obj(self, name: str) -> MP:
        """Get / create object by name from pool."""
        return self.get_tuple_obj("pool", name=name)

    @override
    async def activate(self):  # type: ignore
        result = await self.show_in_dialog()
        if result["value"] is False:
            raise asyncio.CancelledError
        obj = self.get_obj(self.obj_name.value)
        self.obj_name.value = ""
        return await obj.activate()
