from src.utils.pagination import PaginationParams, paginate, paginated_response

def test_pagination_params_defaults():
    params = PaginationParams()
    assert params.page == 1
    assert params.size == 20
    assert params.offset == 0

def test_pagination_params_caps_size():
    params = PaginationParams(size=5000)
    assert params.size == 100

def test_pagination_params_offset():
    params = PaginationParams(page=3, size=15)
    assert params.offset == 30

class MockQuery:
    def __init__(self):
        self._offset = None
        self._limit = None

    def count(self): return 96
    def offset(self, off):
        self._offset = off
        return self
    def limit(self, lim):
        self._limit = lim
        return self
    def all(self):
        return ["item1", "item2"]

def test_paginate():
    q = MockQuery()
    params = PaginationParams(page=2, size=10)
    items, total = paginate(q, params)
    assert total == 96
    assert items == ["item1", "item2"]
    assert q._offset == 10
    assert q._limit == 10

def test_paginated_response():
    params = PaginationParams(page=2, size=10)
    res = paginated_response(["a", "b"], 50, params)
    assert res["data"] == ["a", "b"]
    assert res["total"] == 50
    assert res["page"] == 2
    assert res["size"] == 10
