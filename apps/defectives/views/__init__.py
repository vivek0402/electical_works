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
from .pieces import defective_pieces, piece_detail, pieces_bulk

__all__ = [
    "batch_add",
    "batch_detail",
    "batch_dispatch",
    "batch_new",
    "batch_remove",
    "batch_settle",
    "defective_pieces",
    "mark_defective",
    "piece_detail",
    "pieces_bulk",
    "return_batches",
]
