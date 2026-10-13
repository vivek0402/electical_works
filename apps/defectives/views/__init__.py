"""Defectives screens: marking pieces, return batches and the piece card. URL names live in ../urls.py."""

from .batches import (
    batch_add,
    batch_detail,
    batch_dispatch,
    batch_new,
    batch_remove,
    batch_settle,
    return_batches,
)
from .marking import mark_defective
from .pieces import piece_detail

__all__ = [
    "batch_add",
    "batch_detail",
    "batch_dispatch",
    "batch_new",
    "batch_remove",
    "batch_settle",
    "mark_defective",
    "piece_detail",
    "return_batches",
]
