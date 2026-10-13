"""Parse the defectives list screens' GET params once; views and Excel exports share them."""

from dataclasses import dataclass

from apps.inventory.filters import _obj
from apps.inventory.models import Company

from .models import BATCH_LABELS


@dataclass
class BatchFilters:
    company: Company | None
    status: str  # one of BATCH_LABELS, or "" for any


def batch_filters(params):
    status = params.get("status", "")
    return BatchFilters(_obj(Company, params.get("company")), status if status in BATCH_LABELS else "")
