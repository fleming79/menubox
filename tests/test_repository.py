from typing import Self, cast

import traitlets

import menubox as mb
from menubox import HasHome, Menubox
from menubox import trait_factory as tf
from menubox.repository import Repository


class SelectRepositoryWidget(HasHome, Menubox):
    select_repository = tf.SelectRepository(cast(Self, 0))
    views = traitlets.Dict({"Widgets": "select_repository"})


async def test_select_repository(home: mb.Home):
    w = SelectRepositoryWidget(home=home)
    assert w is w.select_repository.parent
    repo = Repository(home=home, name="new repository")
    await repo.wait_tasks()
    await repo.button_save_persistence_data.start()
    # Test select an existing repository
    await w.select_repository.update_repository_name_options()
    assert repo.name in w.select_repository.repository_name.options
    w.select_repository.repository_name.value = repo.name
    assert w.select_repository.repository is repo
