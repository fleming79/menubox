from __future__ import annotations

from typing import TYPE_CHECKING, Generic, Self, cast, override

import traitlets
from ipylab import Fixed

from menubox import HasHome
from menubox import trait_factory as tf
from menubox.filesystem import Filesystem
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
    views = traitlets.Dict({"Main": "target_filesystem"})
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


class SelectRepository(HasHome, MenuboxVT, Generic[H]):
    """Select or create a new repository."""

    box_center = None
    repository = tf.Repository(cast(Self, None))
    repository_name = tf.Combobox(
        cast(Self, None),
        description="Repository",
        tooltip="Add a new repository using the repository set below",
        layout={"width": "max-content"},
    ).hooks(
        on_set=lambda c: c["parent"]._update_repository_name_options(),
    )
    button_select_repository = tf.Button_menu(description="…", tooltip="Select/create a new repository")
    header_children = StrTuple()
    views = traitlets.Dict({"Main": ["repository_name", "button_select_repository"]})
    value_traits = NameTuple(*MenuboxVT.value_traits, "repository", "repository_name")
    value_traits_persist = NameTuple("repository_name")
    parent_link = NameTuple("repository")

    @override
    def on_change(self, change: ChangeType):
        super().on_change(change)
        if change["name"] == "repository":
            name = self.repository.name
            if name not in self.repository_name.options:
                self.repository_name.options = (*self.repository_name.options, name)
                self.repository.button_save_persistence_data.start()
            self.repository_name.value = name
        match change["owner"]:
            case self.repository_name:
                name = self.repository_name.value
                if isinstance(name, str):
                    self.repository = Repository(name=name, home=self.home)

    def _update_repository_name_options(self):
        options = Repository.list_stored_datasets(self.repository.filesystem)
        # Repository.singular.instances
        if "default" not in options:
            options = (*options, "default")
        self.repository_name.options = options

    @override
    async def button_clicked(self, b: Button):
        await super().button_clicked(b)
        match b:
            case self.button_select_repository:
                repository = Repository(name=self.repository_name.value, home=self.home)
                await repository.activate()
