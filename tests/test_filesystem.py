import asyncio
import pathlib
import tempfile

import pytest

from menubox.filesystem import Filesystem


async def test_filesystem():
    root = tempfile.mkdtemp()
    fs = await Filesystem(url=root).activate()

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
    assert fs.tasks
    await fs.wait_tasks()
    assert new_folder.exists()

    # create a file
    fs.url.value += "/a second new folder/and a new file.txt"
    fname = fs.url.value
    await fs.wait_tasks()
    fs.button_add.click()
    assert fs.tasks
    await fs.wait_tasks()
    assert pathlib.Path(fname).is_file()
    with pytest.raises(TimeoutError):
        async with asyncio.Timeout(1):
            await fs.get_relative_path()
    fs.read_only = True
