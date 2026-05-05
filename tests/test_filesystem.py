import pathlib

from menubox.filesystem import Filesystem


async def test_filesystem(tmp_path: pathlib.Path):
    root = tmp_path.as_posix()
    fs = await Filesystem(url=root)

    # Test root
    fs.url.value = "C:/"
    await fs.wait_pending()
    # create a folder
    await fs.wait_pending()
    new_folder = pathlib.Path(root, "a new folder")
    fs.url.value = new_folder.as_posix()
    await fs.wait_pending()
    assert fs.url.value == new_folder.as_posix()
    fs.button_add.click()
    assert fs.pending
    await fs.wait_pending()
    assert new_folder.exists()

    # create a file
    fs.url.value += "/a second new folder/and a new file.txt"
    fname = fs.url.value
    await fs.wait_pending()
    fs.button_add.click()
    assert fs.pending
    await fs.wait_pending()
    assert pathlib.Path(fname).is_file()
    fs.read_only = True
