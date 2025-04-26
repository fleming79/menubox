from __future__ import annotations

from typing import TYPE_CHECKING, Generic, Self, cast, override

import traitlets
from ipylab import Fixed

from menubox import mb_async
from menubox import trait_factory as tf
from menubox.filesystem import Filesystem, HasFilesystem
from menubox.menuboxvt import MenuboxVT
from menubox.persist import MenuboxPersist
from menubox.trait_types import ChangeType, H, NameTuple, StrTuple

if TYPE_CHECKING:
    from ipywidgets import Button

    from menubox.hashome import Home


class Repository(MenuboxPersist):
    SINGLE_BY = ("home", "name")
    KEEP_ALIVE = True
    FANCY_NAME = "Repository"

    _repository_init_called = False
    title_description = traitlets.Unicode("<b>Repository: &emsp; {self.name}</b>")
    title_description_tooltip = traitlets.Unicode("{self.repository}")
    target_filesystem = Fixed[Self, Filesystem](lambda _: Filesystem())
    box_center = None
    views = tf.ViewDict(cast(Self, 0), {"Main": lambda p: p.target_filesystem})
    value_traits_persist = NameTuple("target_filesystem")

    def __init__(self, name: str, home: Home | str):
        if self._repository_init_called:
            return
        self._repository_init_called = True
        super().__init__(name=name)

    @override
    async def init_async(self):
        await super().init_async()
        await self.target_filesystem.wait_init_async()

    def load_value(self, data):
        if isinstance(data, dict) and "protocol" in data:
            # The legacy version of Repository was a subclass of Filesystem.
            data = {"target_filesystem": data}
        return super().load_value(data)


class SelectRepository(HasFilesystem, MenuboxVT, Generic[H]):
    """Select or create a new repository."""

    box_center = None
    repository = tf.InstanceHP(cast(Self, 0), klass=Repository).configure(tf.IHPMode.X__N)
    repository_name = tf.Combobox(
        cast(Self, 0),
        description="Repository",
        tooltip="Add a new repository using the repository set below",
        layout={"width": "max-content"},
    ).hooks(
        on_set=lambda c: c["parent"].update_repository_name_options(),
    )
    button_select_repository = tf.Button_menu(description="…", tooltip="Select/create a new repository")
    header_children = StrTuple()
    views = tf.ViewDict(cast(Self, 0), {"Main": lambda p: [p.repository_name, p.button_select_repository]})
    value_traits = NameTuple(*MenuboxVT.value_traits, "repository", "repository_name")

    @override
    def on_change(self, change: ChangeType):
        super().on_change(change)
        match change["owner"]:
            case self.repository_name:
                if name := self.repository_name.value:
                    self.set_trait("repository", Repository(name=name, home=self.home))
        if change["name"] == "repository":
            filesystem: Filesystem = getattr(self.repository, "target_filesystem", None) or self.filesystem
            self.set_trait("filesystem", filesystem)

    @mb_async.debounce(0.1)
    async def update_repository_name_options(self):
        self.repository_name.options = await Repository.list_stored_datasets(self.home.filesystem)

    @override
    async def button_clicked(self, b: Button):
        await super().button_clicked(b)
        match b:
            case self.button_select_repository:
                repository = Repository(name=self.repository_name.value, home=self.home)
                await repository.activate()
