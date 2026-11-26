"""The models ocrdoc can use, each measured against the rules it adds to before it was
listed (``bench/areas_bench.py``).  None is needed: every step works without, and a model
that does not lie in the folder given (``--models``) is done without.  How they are
listed, fetched and found: :mod:`doccor.models`.
"""

from __future__ import annotations

from doccor.models import Model

CATALOGUE: tuple[Model, ...] = ()
