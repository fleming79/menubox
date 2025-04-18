from __future__ import annotations

import asyncio
import pathlib
from typing import TYPE_CHECKING, Generic, Self, cast, final, override

import ipywidgets as ipw
import pandas as pd
import traitlets

import menubox
from menubox import mb_async, utils
from menubox import trait_factory as tf
from menubox.async_run_button import AsyncRunButton
from menubox.hashome import HasHome
from menubox.instance import IHPCreate
from menubox.instancehp_tuple import InstanceHPTuple
from menubox.log import TZ
from menubox.menuboxvt import MenuboxVT
from menubox.pack import deep_copy, load_yaml
from menubox.trait_types import MP, ChangeType, R, S, StrTuple, TypedTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable
    from logging import Logger, LoggerAdapter

    from fsspec import AbstractFileSystem

    from menubox.repository import Repository


class HasRepository(HasHome):
    repository = tf.Repository(cast(Self, None))

    def __new__(cls, *, home=None, parent=None, repository=None, **kwargs):
        home = cls.to_home(home, parent)
        if not repository:
            if isinstance(parent, HasRepository):
                repository = parent.repository
            else:
                from menubox.repository import Repository

                if not issubclass(cls, Repository):
                    repository = Repository(name="default", home=home)
        return super().__new__(cls, home=home, parent=parent, repository=repository, **kwargs)


class MenuboxPersist(HasRepository, MenuboxVT, Generic[R]):
    """Persistence of nested settings in yaml files plus persistence of dataframes using
    repository.

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
    ValueTrait objects (including MenuboxVT), settings defined in `value_traits_persist`
    are the `value` so are stored by default.

    Persistence of DataFrames in `value_traits_persist` is not permitted. The tuple
    `dataframe_persist` is provided to persist dataframes in a folder of the same name
    as the yaml data.
    """

    SINGLE_BY = ("repository", "name")
    _PERSIST_TEMPLATE = "settings/{cls.__qualname__}/{name}_v{version}"
    _AUTOLOAD = True
    SINGLE_VERSION = True
    SHOW_TEMPLATE_CONTROLS = True
    DEFAULT_VIEW = None
    title_description = traitlets.Unicode(
        "<b>{self.FANCY_NAME or self.__class__.__qualname__}&emsp;"
        "{self.name.replace('_',' ').capitalize()}"
        "{'' if self.SINGLE_VERSION else f' V{self.version}'}</b>"
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
            src=(c["parent"], "versions"),
            target=(c["obj"], "options"),
        ),
    )
    button_save_persistence_data = tf.InstanceHP(
        cast(Self, None),
        AsyncRunButton,
        lambda c: AsyncRunButton(
            parent=c["parent"],
            cfunc=lambda p: p._button_save_persistence_data_async,
            description="💾",
            tooltip="Save persistence data for current version",
            tasktype=mb_async.TaskType.update,
        ),
    )
    version_widget = tf.InstanceHP(
        cast(Self, None),
        ipw.BoundedIntText,
        lambda c: ipw.BoundedIntText(
            min=1,
            max=1,
            step=1,
            description="Version",
            tooltip="Changing the version will switch to the new version dropping"
            " unsaved changes. \n"
            "If a new version doesn't exist, the present values are retained and can be"
            " saved in the new version.",
            layout={"width": "130px"},
            disabled=c["parent"].SINGLE_VERSION,
        ),
    )
    box_version = tf.Box()
    header_right_children = StrTuple("menu_load_index", *MenuboxVT.header_right_children)
    repository = tf.Repository(cast(Self, None))
    task_loading_persistence_data = tf.Task()
    value_traits = StrTuple(*MenuboxVT.value_traits, "version", "sw_version_load")
    value_traits_persist = StrTuple("saved_timestamp", "description")
    dataframe_persist = StrTuple()


    @classmethod
    def validate_name(cls, name: str) -> str:
        return utils.sanatise_filename(name).lower()

    def _update_versions(self) -> None:
        self.versions = self.get_persistence_versions(self.repository, self.name, self.log)

    @override
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

    @override
    def on_change(self, change: ChangeType) -> None:
        super().on_change(change)
        if not self._Menubox_init_complete:
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

    async def _button_save_persistence_data_async(self, version: int | None = None):
        """Use button_save.start to get an awaitable task."""
        repo = self.repository
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
        """Asynchronously saves dataframes to the repository.

        Iterates through the dataframes specified in `self.dataframe_persist`,
        skipping empty dataframes.  Constructs a file path for each dataframe
        based on the given name, version, and dotted name, then saves the
        dataframe to the repository using an asynchronous thread.

        Args:
            name (str): The name associated with the dataframes to be saved.
            version (int): The version number associated with the dataframes.
        """
        repo = self.repository
        for dotted_name in self.dataframe_persist:
            df: pd.DataFrame = utils.getattr_nested(self, dotted_name)
            if df.empty:
                continue
            path = repo.to_path(self.get_df_filename(name, version, dotted_name))
            await mb_async.to_thread(self.save_dataframe, df, repo.fs, path)
            self.log.info(f"Saved {path}")

    async def get_dataframes_async(self, name: str, version: int) -> dict[str, pd.DataFrame]:
        """Asynchronously retrieves a dictionary of pandas DataFrames.

        Args:
            name (str): The name associated with the DataFrames.
            version (int): The version number associated with the DataFrames.

        Returns:
            dict[str, pd.DataFrame]: A dictionary where keys are dotted names
            and values are the corresponding pandas DataFrames.  Returns an
            empty dictionary if no DataFrames are found.
        """
        repo = self.repository
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
        """Generates a base string for persistence keys.

        The base string incorporates the class name, a provided name, and a version number.
        It is used as a foundation for constructing keys used to persist and retrieve data.

        Args:
            cls: The class for which the persistence base is being generated.
            name: A descriptive name to include in the persistence base.
            version: An integer or string representing the version of the data structure. Must be >= 1.

        Returns:
            A string formatted as '{cls.__qualname__}.{name}.v{version}', all lowercased.

        Raises:
            ValueError: If the version is None, empty, or less than 1.
        """
        if not version or not isinstance(version, str) and version < 1:
            msg = f"version must be >= 1 but is {version}"
            raise ValueError(msg)
        return utils.fstr(cls._PERSIST_TEMPLATE, cls=cls, name=name, version=version).lower()

    @classmethod
    def list_stored_datasets(cls, repository: Repository) -> list[str]:
        """List the names of all stored datasets in the given home.

        The names are sorted alphabetically.

        Args:
            repository: The the repository to search.

        Returns:
            A list of dataset names.
        """
        datasets = set()
        ptn = repository.to_path(cls._get_persist_name("*", "*"))
        for f in repository.fs.glob(str(ptn)):
            datasets.add(utils.stem(f).rsplit("_v", maxsplit=1)[0])  # type: ignore
        return sorted(datasets)

    @classmethod
    def get_df_filename(cls, name: str, version: int, dotted_name: str) -> str:
        """Generates the filename for a DataFrame to be persisted.

        Args:
            name (str): The name of the menu.
            version (int): The version of the menu.
            dotted_name (str): The dotted name of the DataFrame.

        Returns:
            str: The filename for the DataFrame.
        """
        base = cls.get_persistence_base(name, version)
        return pathlib.Path(base, utils.sanatise_filename(f"{dotted_name}.parquet")).as_posix()

    @classmethod
    def get_persistence_versions(
        cls, repository: Repository, name: str, log: Logger | LoggerAdapter | None = None
    ) -> tuple[int, ...]:
        """Get all persistence versions for a given name.

        Args:
            home: The home directory or a Home object.
            name: The name of the persisted object.
            log: An optional logger.

        Returns:
            A tuple of sorted version numbers.
            If SINGLE_VERSION is True, returns (1,) if version 1 exists, otherwise ().
            Returns () if any error occurs.
        """
        path = repository.to_path(cls._get_persist_name(name, "*"))
        files = repository.fs.glob(str(path))
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

    @override
    async def get_center(self, view: str | None):
        if not self.name:
            view = self._CONFIGURE_VIEW
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
                version = self._to_version(version)
                data = await mb_async.to_thread(
                    self.get_persistence_data, self.repository, self.name, self._to_version(version)
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
    def get_persistence_data(cls, repository: Repository, name: str, version: int | None = None) -> dict:
        """
        Retrieves persistence data for a given name and version from a specified home directory.

        Args:
            home: The home directory or Home object where the persistence data is stored.
            name: The name of the persistence data.
            version: The version of the persistence data to retrieve. If None, the latest version is retrieved.

        Returns:
            A dictionary containing the persistence data. Returns an empty dictionary if no data is found or if the data is not a dictionary.

        Raises:
            FileNotFoundError: If the file containing the persistence data is not found.
            TypeError: If the loaded data is not a dictionary.
        """
        versions = cls.get_persistence_versions(repository, name)
        if not versions or version is not None and version not in versions:
            return {}
        if version is None:
            version = max(versions)
        fname = repository.to_path(cls._get_persist_name(name, version))
        if repository.fs.isfile(fname):
            with repository.fs.open(str(fname)) as file:
                data = load_yaml(file)
                if isinstance(data, dict):
                    return data
                if data:
                    msg = f"Expect dict but got {data}"
                    raise TypeError(msg)
                return {}
        else:
            msg = f"{fname!s} in {repository=}"
            raise FileNotFoundError(msg)

    def get_latest_version(self) -> int:
        """Retrieves the latest version number from the available versions.

        If no versions are available, it returns a default version number of 1.

        Returns:
            int: The latest version number, or 1 if no versions are available.
        """
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
class MenuboxPersistPool(HasRepository, MenuboxVT, Generic[S, MP]):
    """A Menubox that can load MenuboxPersist instances into the shell."""

    SINGLE_BY = ("klass", "repository")
    RENAMEABLE = False
    pool = InstanceHPTuple[Self, MP](
        traitlets.Instance(MenuboxPersist), factory=lambda c: c["parent"].factory_pool(**c["kwgs"])
    ).hooks(
        update_item_names=("name", "versions"),
        set_parent=True,
        close_on_remove=False,
    )
    obj_name = tf.Combobox(cast(Self, None), placeholder="Enter name or select existing", continuous_update=True).hooks(
        on_set=lambda c: (
            c["parent"].update_names(),
            c["parent"].dlink(src=(c["parent"], "names"), target=(c["obj"], "options")),
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
        kwgs["repository"] = self.repository
        if self._factory:
            return self._factory(IHPCreate(name="", parent=self, kwgs=kwgs, klass=self.klass))
        return self.klass(**kwgs)

    def update_names(self) -> list[str]:
        """List the stored datasets for the klass."""
        names = self.klass.list_stored_datasets(self.repository)
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
