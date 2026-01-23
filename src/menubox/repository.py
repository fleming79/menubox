from __future__ import annotations

from typing import TYPE_CHECKING, Generic, Self, cast, override

from async_kernel.common import Fixed

from menubox import mb_async
from menubox.filesystem import Filesystem, HasFilesystem
from menubox.menuboxvt import MenuboxVT
from menubox.persist import MenuboxPersist
from menubox.trait_factory import TF
from menubox.trait_types import ChangeType, H, NameTuple, StrTuple

if TYPE_CHECKING:
    from ipywidgets import Button


class Repository(MenuboxPersist):
    SINGLE_BY = ("home", "name")
    KEEP_ALIVE = True
    FANCY_NAME = "Repository"

    _repository_init_called = False
    title_description = TF.Str("<b>Repository: &emsp; {self.name}</b>")
    title_description_tooltip = TF.Str("{self.repository}")
    target_filesystem = Fixed[Self, Filesystem](lambda _: Filesystem())
    box_center = None
    views = TF.ViewDict(cast("Self", 0), {"Main": lambda p: p.target_filesystem})
    value_traits_persist = NameTuple[Self](lambda p: (p.target_filesystem,))

    def __init__(self, name: str, **kwgs):
        if self._repository_init_called:
            return
        self._repository_init_called = True
        super().__init__(name=name)

    @override
    async def init_async(self):
        await super().init_async()
        await self.target_filesystem

    def load_value(self, data):
        if isinstance(data, dict) and "protocol" in data:
            # The legacy version of Repository was a subclass of Filesystem.
            data = {"target_filesystem": data}
        return super().load_value(data)


class SelectRepository(HasFilesystem, MenuboxVT, Generic[H]):
    """Select or create a new repository."""

    box_center = TF.HBox()
    repository = TF.InstanceHP(Repository).configure(TF.IHPMode.X__N)
    repository_name = TF.Combobox(
        cast("Self", 0),
        description="Repository",
        placeholder="Home repository",
        tooltip="Enter the name of the repository to use. A blank name is the home default repository. The repository will appear in the list only once it has been saved.",
        layout={"width": "max-content"},
        continuous_update=False,
    ).hooks(
        on_set=lambda c: c["owner"].update_repository_name_options(),
    )
    button_select_repository = TF.Button(
        cast("Self", 0),
        TF.CSScls.button_menu,
        icon="ellipsis-h",
        tooltip="Select/create a new repository (Enter a new repository name to create a new repository).",
    )
    title_description = TF.Str("root: {self.filesystem.root}")
    header_children = StrTuple()
    views = TF.ViewDict(
        cast("Self", 0),
        {
            "Main": lambda p: [
                p.repository_name,
                p.button_select_repository,
                p.html_title,
            ]
        },
    )
    value_traits = NameTuple[Self](
        lambda p: (
            *MenuboxVT.value_traits,
            p.repository,
            p.repository_name,
            p.filesystem.url,
            p.repository.saved_timestamp,  # pyright: ignore[reportOptionalMemberAccess]
        )
    )

    @override
    def on_change(self, change: ChangeType):
        super().on_change(change)
        match change["owner"]:
            case self.repository_name:
                if name := self.repository_name.value:
                    self.set_trait("repository", Repository(name=name, home=self.home))
                else:
                    self.set_trait("repository", self.repository)
        if change["name"] == "repository":
            filesystem: Filesystem = getattr(self.repository, "target_filesystem", None) or self.filesystem
            self.set_trait("filesystem", filesystem)
        self.mb_refresh()
        self.update_repository_name_options()

    @mb_async.debounce(0.1)
    async def update_repository_name_options(self):
        self.repository_name.options = await Repository.list_stored_datasets(self.home.filesystem)

    @override
    async def button_clicked(self, b: Button):
        await super().button_clicked(b)
        match b:
            case self.button_select_repository:
                self.update_repository_name_options()
                if not (name := self.repository_name.value):
                    return
                repository = Repository(name=name, home=self.home)
                await repository.activate(add_to_shell=True)
