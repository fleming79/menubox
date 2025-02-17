import pathlib
import tempfile

from menubox.home import Home
from menubox.repository import Repository


async def test_home():
    root = pathlib.Path(tempfile.mkdtemp())
    root2 = pathlib.Path(tempfile.mkdtemp())

    home1 = Home(str(root))
    assert home1.repository.home is home1
    assert home1.repository.url.value == root.as_posix()
    assert Home(str(root)) is home1

    home2 = Home(str(root2))
    assert home2 is not home1

    repo1 = await home2.get_repository("repo")  # type:Repository
    repo1a = await home2.get_repository("repo")
    assert repo1a is repo1, "Should return the same repository"
    repo1.close(force=True)
    assert repo1.closed
    repo1b = await home2.get_repository("repo")
    assert repo1b is not repo1, "Should have made a new version as the last was closed"

    assert isinstance(repo1, Repository)
    repo2 = await home1.get_repository("repo")
    assert repo1 is not repo2, "Repositories are unique by home and name"
