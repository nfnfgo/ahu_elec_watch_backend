from pydantic import BaseModel

from sqlalchemy import Select
from sqlalchemy.orm import DeclarativeBase


class SQLBaseModel(DeclarativeBase):
    pass


class PaginationConfig(BaseModel):
    """
    Pagination tool class that used to add pagination to select statement::

        stmt : Select
        pagi_conf = PaginationConfig(size=..., limit=...)
        pagi_conf.use_on(stmt)

    Also since this class is extend from ``pydantic.BaseModel``, so it can be used as a dependency of
    FastAPI method::

        @fastApiRouter.get('/test')
        def test_endpoint(pagi_conf : PaginationConfig):
            pass
    """
    # how many rows contains in a page
    size: int = 20

    # zero-index page number
    index: int

    def use_on(self, select_stmt: Select):
        offset = self.size * self.index
        limit = self.size
        return select_stmt.limit(limit).offset(offset)