from menubox.widgets import SelectMultipleValidate


async def test_SelectMultipleValidate():
    obj = SelectMultipleValidate()
    obj.options = (1, 2, 3)
    obj.value = [1, 4]
    assert obj.value == (1,)
