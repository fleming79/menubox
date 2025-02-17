import ipywidgets as ipw
import traitlets

import menubox as mb
from menubox.pack import deep_copy, to_dict, to_yaml, to_yaml_dict


class DemoObj(mb.MenuBoxVT):
    _STASH_DEFAULTS = True
    value_traits_persist = mb.NameTuple("a", "b")
    a = traitlets.Tuple((1, 2, 3, 4))
    b = traitlets.Dict({"a": 1, "b": "2"})
    c = traitlets.Instance(ipw.Text, ())


async def test_convert_yaml(home: mb.Home):
    obj = DemoObj(home=home)
    assert obj.to_dict() == obj._DEFAULTS
    _, b, _ = obj.a, obj.b, obj.c

    # to_yaml & to_dict
    obj.link(
        (obj, "b"),
        (obj.c, "value"),
        transform=(to_yaml, to_dict),
    )
    assert obj.b == b, "'linking shouldn't change the value."
    assert obj.c.value == "a: 1\nb: '2'"
    obj.c.value = "D: 3"
    assert obj.b == {"D": 3}

    # to_yaml_dict
    json_text = obj.to_json()
    val = deep_copy(obj)
    j_val = to_dict(json_text)
    assert val == j_val

    yaml_text = to_yaml_dict(val)
    y_val = to_dict(yaml_text)
    assert val == y_val
