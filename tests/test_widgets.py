from menubox.widgets import DropdownAdd, SelectMultipleValidate


async def test_SelectMultipleValidate():
    obj = SelectMultipleValidate()
    obj.options = (1, 2, 3)
    obj.value = [1, 4]
    assert obj.value == (1,)


def test_dropdown_add():
    dd = DropdownAdd()
    dd.value = "abc"
    assert "abc" in dd.options
    assert dd.value == "abc"
    dd.options = ()
    assert not dd.options
