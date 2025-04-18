from typing import Self, cast

import traitlets

import menubox as mb
from menubox import Menubox
from menubox import trait_factory as tf
from menubox.repository import HasRepository, Repository


class SelectRepositoryWidget(HasRepository, Menubox):
    select_repository = tf.SelectRepository(cast(Self, None))
    views = traitlets.Dict({"Widgets": "select_repository"})


async def test_select_repository(home: mb.Home):
    w = SelectRepositoryWidget(home=home)
    assert w is w.select_repository.parent
    assert w.repository is w.select_repository.repository
    repo = Repository(home=home, name="new repository")
    await repo.wait_tasks()
    await repo.button_save_persistence_data.start()
    # Test select an existing repository
    w.select_repository._update_repository_name_options()
    assert repo.name in w.select_repository.repository_name.options
    w.select_repository.repository_name.value = repo.name
    assert w.select_repository.repository is repo

    # Test directly setting repository updates the name of the repository sele
    repo2 = Repository(home=home, name="second new repository")
    await repo2.wait_tasks()
    await repo2.button_save_persistence_data.start()
    w.select_repository.repository = repo2
    assert w.select_repository.repository_name.value == repo2.name

    w.repository = repo
    assert w.select_repository.repository is repo
