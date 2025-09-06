import pathlib

import anyio
import pytest

from menubox.filesystem import Filesystem


async def test_filesystem(tmp_path: pathlib.Path):
    root = tmp_path.as_posix()
    fs = await Filesystem(url=root)

    # Test root
    fs.url.value = "C:/"
    await fs.wait_tasks()
    # create a folder
    await fs.wait_tasks()
    new_folder = pathlib.Path(root, "a new folder")
    fs.url.value = new_folder.as_posix()
    await fs.wait_tasks()
    assert fs.url.value == new_folder.as_posix()
    fs.button_add.click()
    assert fs.futures
    await fs.wait_tasks()
    assert new_folder.exists()

    # create a file
    fs.url.value += "/a second new folder/and a new file.txt"
    fname = fs.url.value
    await fs.wait_tasks()
    fs.button_add.click()
    assert fs.futures
    await fs.wait_tasks()
    assert pathlib.Path(fname).is_file()
    with pytest.raises(TimeoutError):
        with anyio.fail_after(0.1):
            await fs.get_relative_path()
    fs.read_only = True
