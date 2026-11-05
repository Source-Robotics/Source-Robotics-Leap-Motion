"""Small standard-library backports needed only on Python 3.10."""

import sys

if sys.version_info >= (3, 11):
    from typing import Self

    import tomllib
else:
    import tomli as tomllib
    from typing_extensions import Self

__all__ = ["Self", "tomllib"]
