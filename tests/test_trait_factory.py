import pytest
from traitlets import TraitError

from menubox import HasParent
from menubox.trait_factory import TF


class TestTraitFactory:
    async def test_base_types(self):
        class BaseTest(HasParent):
            str = TF.Str()
            int = TF.Int()
            float = TF.Float()
            dict = TF.Dict()
            set = TF.Set()

        base = BaseTest()
        assert isinstance(base.str, str)
        assert isinstance(base.int, int)
        assert isinstance(base.float, float)
        assert isinstance(base.dict, dict)
        assert isinstance(base.set, set)

    async def test_parent(self):
        p = HasParent()
        assert p.parent is None
        obj = HasParent(parent=p)
        assert obj.parent is p
        with pytest.raises(TraitError, match="Unable to set parent of"):
            p.parent = obj
