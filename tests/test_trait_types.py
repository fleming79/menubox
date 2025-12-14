from typing import Self, cast

from traitlets import HasTraits, Integer, Unicode

from menubox.trait_types import FromParent


def test_parent_items():
    """Tests that FromParent can be initialized with a callable default value."""

    class HP(HasTraits):
        a = Unicode("a")
        b = Integer(None, allow_none=True)
        items = FromParent(cast("Self", 0), lambda p: (p.a, p.b))

        def get_items(self):
            return self.items(self)

    p = HP()
    assert p.get_items() == (p.a, p.b)

    p.set_trait("items", lambda p: p.a)
    assert p.get_items() == p.a
