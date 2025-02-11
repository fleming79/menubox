import pandas as pd

import menubox as mb
from menubox.defaults import NO_VALUE, is_no_value


def test_NO_VALUE():
    assert is_no_value(NO_VALUE)
    assert is_no_value(mb.defaults.NO_DEFAULT)
    assert str(NO_VALUE) == "<NA>"
    assert NO_VALUE, "For a bool test it should test as True"
    assert NO_VALUE == "<NA>"
    assert NO_VALUE == pd.NA
    assert NO_VALUE != True  # noqa: E712
    assert NO_VALUE != 0
    assert NO_VALUE != 0.0
    assert pd.isna(NO_VALUE)
    dfa = pd.DataFrame([NO_VALUE])
    assert len(dfa) == 1
    assert str(float(NO_VALUE)) == "nan"  # type: ignore
    assert dfa.dtypes[0].kind == "f", 'NO_VALUE is also float("nan")'
    assert not is_no_value(dfa), "Dataframe should never be 'not a value'"
