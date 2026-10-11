"""Server-side sort + paging for list screens. GET params: sort, dir (asc|desc), page, size (10|25|50)."""

from django.core.paginator import Paginator

SIZES = (10, 25, 50)


def _key(value):
    if value is None:
        return (1, "")
    return (0, value.lower()) if isinstance(value, str) else (0, value)


def sort_and_page(request, rows, sorters, default_sort, default_dir="asc"):
    """rows: list; sorters: {key: row -> value}. Unknown params fall back to safe defaults."""
    sort = request.GET.get("sort") if request.GET.get("sort") in sorters else default_sort
    direction = request.GET.get("dir") if request.GET.get("dir") in ("asc", "desc") else default_dir
    rows = sorted(rows, key=lambda r: _key(sorters[sort](r)), reverse=direction == "desc")
    try:
        size = int(request.GET.get("size", SIZES[0]))
    except ValueError:
        size = SIZES[0]
    if size not in SIZES:
        size = SIZES[0]
    page = Paginator(rows, size).get_page(request.GET.get("page"))
    return {"page": page, "sort": sort, "dir": direction, "size": size, "sizes": SIZES, "total": len(rows)}
