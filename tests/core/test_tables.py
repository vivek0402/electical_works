from django.test import RequestFactory

from apps.core.tables import sort_and_page

ROWS = [{"code": c, "n": n} for c, n in [("b", 2), ("a", 3), ("C", 1)] * 5]
SORTERS = {"code": lambda r: r["code"], "n": lambda r: r["n"]}


def run(qs):
    return sort_and_page(RequestFactory().get("/x" + qs), ROWS, SORTERS, "code")


def test_default_sort_is_case_insensitive_and_pages_by_10():
    t = run("")
    assert [r["code"] for r in t["page"].object_list][:5] == ["a"] * 5
    assert t["page"].paginator.per_page == 10 and t["total"] == 15


def test_sort_desc_and_size():
    t = run("?sort=n&dir=desc&size=25")
    assert t["page"].object_list[0]["n"] == 3 and t["size"] == 25 and t["dir"] == "desc"


def test_bad_params_fall_back():
    t = run("?sort=evil&dir=sideways&size=999&page=abc")
    assert (t["sort"], t["dir"], t["size"], t["page"].number) == ("code", "asc", 10, 1)
