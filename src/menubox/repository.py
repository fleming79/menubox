from __future__ import annotations

from typing import TYPE_CHECKING, Self, override

import traitlets
from ipylab.common import Fixed

from menubox import mb_async, utils
from menubox import trait_factory as tf
from menubox.filesystem import Filesystem
from menubox.hasparent import Parent
from menubox.home import Home
from menubox.menuboxvt import MenuboxVT
from menubox.persist import MenuboxPersist
from menubox.shuffle import ObjShuffle
from menubox.trait_types import ChangeType, NameTuple, StrTuple

if TYPE_CHECKING:
    from ipywidgets import Button


class Repository(Filesystem, MenuboxPersist):
    SINGLETON_BY = ("home", "name")
    KEEP_ALIVE = True
    FANCY_NAME = "Repository"
    folders_only = traitlets.Bool(True)
    disabled = traitlets.Bool(False, read_only=True)
    value_traits_persist = NameTuple("protocol", "url", "kw")
    title_description = traitlets.Unicode("<b>Repository: &emsp; {self.name}</b>")
    title_description_tooltip = traitlets.Unicode("{self.repository}")
    parent = Parent(Home)

    @property
    def root(self):
        return self.url.value

    def __init__(self, name: str, **kwargs):
        if self._HasParent_init_complete:
            return
        if name == "default":
            self._configure_as_default_repo()
        super().__init__(name=name, **kwargs)
        self.parent = self.home
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


class Repositories(ObjShuffle):
    SINGLETON_BY = ("home",)
    obj_cls = traitlets.Type(Repository)


class SelectRepository(MenuboxVT):
    """Select a repository by name for a parent.

    ## Suggestion for usage

    ``` code
    class MenuboxVTR(MenuboxVT):
        select_repository = tf.SelectRepository()

    ```
    """

    box_center = None
    repositories: Fixed[Self, Repositories] = Fixed(lambda c: Repositories(home=c["owner"].home))
    repository_name = tf.Dropdown(
        description="Repository",
        tooltip="Add a new repository using the repository set below",
        layout={"width": "max-content"},
    ).configure(
        dlink={
            "source": ("repositories.sw_obj", "options"),
            "target": "options",
            "transform": lambda options: (*options, *(("default",) if "default" not in options else ())),
        }
    )
    button_select_repository = tf.Button_menu(description="…", tooltip="Select/create a new repository")
    header_children = StrTuple()
    views = traitlets.Dict({"Main": ["repository_name", "button_select_repository"]})
    parent_link = NameTuple("repository")
    value_traits = NameTuple(*MenuboxVT.value_traits, "repository", "repository_name")
    value_traits_persist = NameTuple("repository_name")

    @override
    def on_change(self, change: ChangeType):
        super().on_change(change)
        if change["name"] == "repository":
            self.repositories.update_sw_obj_options()
            name = self.repository.name
            if name not in self.repository_name.options:
                self.repository_name.options = (*self.repository_name.options, name)
                self.repository.button_save_persistence_data.start()
            self.repository_name.value = name
        match change["owner"]:
            case self.repository_name:
                name = self.repository_name.value
                if isinstance(name, str):
                    self.repository = Repository(home=self.home, name=name)
        self._update_button_select_repository_info()

    def _update_button_select_repository_info(self):
        repo = self.repository
        self.button_select_repository.tooltip = (
            f"Current repository: '{repo.name}'"
            + "\n".join(f"{k}: {v}" for k, v in repo.value().items())
            + "\nClick to edit repositories."
        )

    @override
    async def button_clicked(self, b: Button):
        await super().button_clicked(b)
        match b:
            case self.button_select_repository:
                self.repositories.activate()
