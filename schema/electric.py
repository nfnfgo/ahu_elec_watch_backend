import time

from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import BIGINT
from pydantic import BaseModel

from .sql import SQLBaseModel


class BalanceRecord(BaseModel):
    """
    The schema used by a balance record.
    """

    # The 10 digital float unix timestamp when this record was caught
    timestamp: float = 0

    # The current recorded balance
    light_balance: float = 0

    # Current balance in ac account
    ac_balance: float = 0

    @classmethod
    def from_info_dict(cls, info_dict):
        """
        Factory method to create a BalanceRecord instance from a info dict.
        :param info_dict:
        :return:
        """
        return cls(
            timestamp=time.time(),
            light_balance=info_dict['light_balance'],
            ac_balance=info_dict['ac_balance']
        )


class SQLRecord(SQLBaseModel):
    __tablename__ = 'record'

    timestamp: Mapped[float] = mapped_column(
        primary_key=True,
        comment='The timestamp this record has been caught')
    light_balance: Mapped[float] = mapped_column(comment='The balance or general account')
    ac_balance: Mapped[float] = mapped_column(comment='The balance of air conditioner account')


class Statistics(BaseModel):
    """
    Class used as response model for statistics info
    """
    # The timestamp when this statistics generated
    timestamp: float
    # Total balance used at last day
    total_last_day: float
    # Total balance used at last 7 days
    total_last_7_days: float
    # A list contains all available record at last 7 day
    record_last_7_days: list[BalanceRecord] = []


class CountInfoOut(BaseModel):
    total: int
    last_7_days: int


TEST_STATISTICS_DICT = {
    'timestamp': 0,
    'total_last_day': 3.54,
    'total_last_7_days': 10.85,
    'record_last_7_days': []
}
