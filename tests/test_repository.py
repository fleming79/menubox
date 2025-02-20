import pathlib

import traitlets

import menubox as mb
from menubox import MenuBoxVT
from menubox import trait_factory as tf
from menubox.repository import Repositories, Repository


class SelectRepositoryWidget(MenuBoxVT):
    select_repository = tf.SelectRepository()
    views = traitlets.Dict({"Widgets": "select_repository"})


async def test_repository(home: mb.Home, tmp_path: pathlib.Path):
    assert home.repository.root == tmp_path.as_posix()
    assert home.repository.home is home
    assert home.repository.parent is home

    rps = Repositories(home=home)
    name = "My custom repo"
    repo = rps.get_obj(name)
    repo2 = rps.get_obj(name)
    assert repo2 is repo
    assert repo2.home is home
    result = rps.show()
    if result:
        await result

    repo3 = Repository(name=name, home=home)
    assert repo3 is repo2


async def test_select_repository(home: mb.Home):
    w = SelectRepositoryWidget(home=home)

    assert w.select_repository.repository is w.home.repository, "Loads the default repo."
    assert w is w.select_repository.parent
    repo = Repository(home=home, name="new repository")
    await repo.wait_tasks()
    await repo.button_save_persistence_data.start()
    w.select_repository.repositories.update_sw_obj_options()
    assert repo.name in w.select_repository.repository_name.options
    w.select_repository.repository_name.value = repo.name
    assert w.repository is repo

    repo2 = Repository(home=home, name="second new repository")
    await repo2.wait_tasks()
    await repo2.button_save_persistence_data.start()
    w.repository = repo2
    assert w.select_repository.repository_name.value == repo2.name
