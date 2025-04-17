from __future__ import annotations

from typing import TYPE_CHECKING, Generic, Self, cast, override

import traitlets

from menubox import mb_async, utils
from menubox import trait_factory as tf
from menubox.filesystem import Filesystem
from menubox.hashome import HasHome
from menubox.hasparent import Parent
from menubox.menuboxvt import MenuboxVTH
from menubox.persist import MenuboxPersist
from menubox.trait_types import ChangeType, H, NameTuple, StrTuple

if TYPE_CHECKING:
    from ipywidgets import Button


class Repository(Filesystem, MenuboxPersist):
    SINGLE_BY = ("home", "name")
    KEEP_ALIVE = True
    FANCY_NAME = "Repository"
    folders_only = traitlets.Bool(True)
    disabled = traitlets.Bool(False, read_only=True)
    value_traits_persist = NameTuple("protocol", "url", "kw")
    title_description = traitlets.Unicode("<b>Repository: &emsp; {self.name}</b>")
    title_description_tooltip = traitlets.Unicode("{self.repository}")

    @property
    def root(self):
        return self.url.value

    def __init__(self, name: str, **kwargs):
        if self._HasParent_init_complete:
            return
        if name == "default":
            self._configure_as_default_repo()
        super().__init__(name=name, **kwargs)
        if not self.url.value:
            self.url.value = self.home_url = self.home.repository.url.value

    def _configure_as_default_repo(self):
        self.folders_only = True
        self.set_trait("disabled", True)
        self.disable_widget("menu_load_index")
        self.read_only = True
        self.disable_widget("template_controls")
        self.viewlist = ("Main",)

    @override
    def on_change(self, change: ChangeType):
        if not self.read_only:
            super().on_change(change)

    def to_path(self, *parts: str):
        """Will join the parts. If a local file system, it will return an absolute path.

        Returns:
            str: posix style.
        """
        if self.protocol.value == "file":
            return utils.joinpaths(self.root, *parts)
        return utils.joinpaths(self.root, *parts)

    async def write_async(self, path: str, data: bytes):
        # write data to path in fs
        await mb_async.to_thread(self.write, path, data)

    def write(self, path: str, data: bytes):
        with self.fs.open(path, "wb") as f:
            f.write(data)  # type: ignore


class SelectRepository(MenuboxVTH, Generic[H]):
    """Select a repository.

    ## Usage

    ``` python
    from typing import Self


    class MyClass(MenuboxVTH):
        select_repository = tf.SelectRepository(cast(Self, None))

        value_traits_persist = mb.StrTuple("select_repository")
    ```
    """

    parent: Parent[H] = Parent(HasHome)  # type: ignore
    box_center = None

    repositories = tf.MenuboxPersistPool(cast(Self, None), Repository)
    repository = tf.Repository(cast(Self, None))
    repository_name = tf.Dropdown(
        cast(Self, None),
        description="Repository",
        tooltip="Add a new repository using the repository set below",
        layout={"width": "max-content"},
    ).hooks(
        on_set=lambda c: (
            utils.weak_observe(c["parent"].repositories, c["parent"]._update_repository_name_options, "names"),
            c["parent"]._update_repository_name_options(),
        )
    )
    button_select_repository = tf.Button_menu(description="…", tooltip="Select/create a new repository")
    header_children = StrTuple()
    views = traitlets.Dict({"Main": ["repository_name", "button_select_repository"]})
    value_traits = NameTuple(*MenuboxVTH.value_traits, "repository", "repository_name")
    value_traits_persist = NameTuple("repository_name")
    parent_link = NameTuple("repository")

    @override
    def on_change(self, change: ChangeType):
        super().on_change(change)
        if change["name"] == "repository":
            self.repositories.update_names()
            name = self.repository.name
            if name not in self.repository_name.options:
                self.repository_name.options = (*self.repository_name.options, name)
                self.repository.button_save_persistence_data.start()
            self.repository_name.value = name
        match change["owner"]:
            case self.repository_name:
                name = self.repository_name.value
                if isinstance(name, str):
                    self.repository = self.repositories.get_obj(name=name)
        self._update_button_select_repository_info()

    def _update_button_select_repository_info(self):
        repo = self.repository
        self.button_select_repository.tooltip = (
            f"Current repository: '{repo.name}'"
            + "\n".join(f"{k}: {v}" for k, v in repo.value().items())
            + "\nClick to edit repositories."
        )

    def _update_repository_name_options(self):
        options = self.repositories.names
        if "default" not in options:
            options = (*options, "default")
        self.repository_name.options = options

    @override
    async def button_clicked(self, b: Button):
        await super().button_clicked(b)
        match b:
            case self.button_select_repository:
                await self.repositories.activate()
