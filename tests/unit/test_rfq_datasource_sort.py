import pytest

from src.datasources.rfq_datasource import RfqDatasource
from src.utils.errors import BadRequestError


class MockQuery:
    def __init__(self):
        self.order_expr = None

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, expr):
        self.order_expr = expr
        return self


class MockSession:
    def __init__(self):
        self.query_obj = MockQuery()

    def query(self, _model):
        return self.query_obj


def test_list_sort_whitelist_accepts_valid_field():
    session = MockSession()
    ds = RfqDatasource(session)

    ds.list(status=["In preparation"], sort="name")

    assert session.query_obj.order_expr is not None
    assert "name" in str(session.query_obj.order_expr)


def test_list_sort_whitelist_accepts_desc_prefix():
    session = MockSession()
    ds = RfqDatasource(session)

    ds.list(status=["In preparation"], sort="-created_at")

    assert session.query_obj.order_expr is not None
    assert "DESC" in str(session.query_obj.order_expr)


def test_list_sort_whitelist_rejects_invalid_field():
    session = MockSession()
    ds = RfqDatasource(session)

    with pytest.raises(BadRequestError) as exc:
        ds.list(status=["In preparation"], sort="workflow_id")

    assert "Invalid sort field" in str(exc.value)
