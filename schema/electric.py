import time
from enum import Enum

from loguru import logger
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import BIGINT
from pydantic import BaseModel, field_validator

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

    @field_validator('light_balance', 'ac_balance')
    @classmethod
    def value_round(cls, value: float):
        """
        Class validator used to validate data to 2 point precision.
        :param value:
        :return:
        """
        # logger.debug(f'Custom Validator Called, Rounding Number: {value} --> {round(value, 2)}')
        return round(value, 2)

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

    timestamp: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=False,
        unique=True,
        comment='The timestamp this record has been caught')
    light_balance: Mapped[float] = mapped_column(comment='The balance or general.py account')
    ac_balance: Mapped[float] = mapped_column(comment='The balance of air conditioner account')


class Statistics(BaseModel):
    """
    Class used as response model for statistics info
    """
    # The timestamp when this statistics generated
    timestamp: float
    # Total balance used at last day
    light_total_last_day: float
    # Total balance used at last 7 days
    light_total_last_week: float
    ac_total_last_day: float
    ac_total_last_week: float


class CountInfoOut(BaseModel):
    total: int
    last_7_days: int


TEST_STATISTICS_DICT = {
    'timestamp': 0,
    'total_last_day': 3.54,
    'total_last_7_days': 10.85,
    'record_last_7_days': []
}


class RecordDataType(str, Enum):
    """
    Define the returned record list data type.

    For each record in the return list:

    - `balance` Returns the balance of that timestamp.
    - `usage` Returns the usage during the previous record and current record.
    """
    balance: str = 'balance'
    usage: str = 'usage'


class PeriodUsageInfoOut(BaseModel):
    """
    Define the daily usage info return type.

    Members:

    - ``start_time`` ``end_time``: The start and end timestamp of the statistics of this record.
    - ``ac_usage`` ``balance_usage``: The usage info of the balance during this duration.
    """
    start_time: int
    end_time: int
    ac_usage: float
    light_usage: float


class UsageConvertConfig(BaseModel):
    """
    Used to store the param of converting record_list to usage list.

    - ``spreading`` If `true`, implement point spreading.
    - ``smoothing`` If `true`, implement points smoothing.
    - ``per_hour_usage``: If `true`, the usage list value will use `usage/h` as unit.
    - ``use_smart_merge``: If `true`, implement smart merge with auto calculated merge ratio.
    - ``merge_ratio``: If NOT `None`, using this merge ratio when implementing smart merge instead of the default one.
    """
    spreading: bool = True
    smoothing: bool = True
    per_hour_usage: bool = True
    use_smart_merge: bool = True
    merge_ratio: int | None = None
