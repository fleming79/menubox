from menubox.hashome import Home


async def test_home():
    home1 = Home("home1")
    assert Home(home1) is home1

    home2 = Home("home2")
    assert home2 is not home1
