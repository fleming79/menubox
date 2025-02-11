import pathlib
import tempfile

from menubox import Home, utils
from menubox.filesystem import Filesystem


async def test_filesystem():
    root = tempfile.mkdtemp()
    home = Home(root)

    fs = Filesystem(home=home, url=root)
    await utils.wait_for(fs.load_view())
    fs.button_update_sw_main.start()
    await fs.wait_update_tasks()

    # Test root
    fs.url.value = "C:/"
    await fs.button_update_sw_main.start()
    # create a folder
    new_folder = pathlib.Path(root, "a new folder")
    fs.url.value = new_folder.as_posix()
    fs.button_add.click()
    assert fs.tasks
    await fs.wait_tasks()
    assert new_folder.exists()

    # create a file
    fs.url.value += "/a second new folder/and a new file.txt"
    fname = fs.url.value
    fs.button_add.click()
    assert fs.tasks
    await fs.wait_tasks()
    assert pathlib.Path(fname).is_file()

    fs.read_only = True
