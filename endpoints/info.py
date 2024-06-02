import time
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Query

from schema.electric import Statistics, BalanceRecord
from provider.database import add_record, get_record_count
from provider import database as provider_db
from schema.electric import BalanceRecord
from schema import electric as elec_schema
from schema import general as gene_schema
from schema.sql import PaginationConfig

from exception import error as exc

# Router for info
# Notice that this router actually do NOT add any prefix
infoRouter = APIRouter()


@infoRouter.get('/statistics', response_model=Statistics, tags=['Statistics'])
async def get_electrical_usage_statistic():
    return await provider_db.get_statistics()


@infoRouter.post('/add_record', tags=['Record'])
async def add_new_record(new_record: BalanceRecord, use_current_timestamp: bool = False):
    """
    Add a record into database.

    When timstamp in `new_record` is negative, use current timestamp forcefully.

    :param new_record: Record need to be added into database.
    :param use_current_timestamp: If `true`, use current timestamp.
    :return:
    """
    # Override timestamp if needed
    if use_current_timestamp or new_record.timestamp < 0:
        new_record.timestamp = time.time()
    await add_record(new_record)


@infoRouter.get('/record_count', response_model=elec_schema.CountInfoOut, tags=['Record', 'Statistics'])
async def record_count():
    return await get_record_count()


@infoRouter.post(
    '/records',
    response_model=list[BalanceRecord],
    tags=['Record'])
async def get_record_list(pagination: PaginationConfig):
    return await provider_db.get_records(pagination)


@infoRouter.get('/latest_record', tags=['Record'], response_model=BalanceRecord)
async def get_lastest_record():
    res = await provider_db.get_records(
        pagination=PaginationConfig(size=1, index=0)
    )
    if len(res) == 0:
        raise exc.NoResultError('No record in database')

    return res[0]


@infoRouter.get('/recent_records', tags=['Record'], response_model=list[BalanceRecord])
async def get_recent_days_records(
        days: Annotated[int, Query(ge=1)] = 7,
        info_type: elec_schema.RecordDataType = elec_schema.RecordDataType.balance):
    """
    Here days actually has been converted to timstamp. That means the earliest limit is set by
    calculating time offset but not using natural day as limit.
    """
    return await provider_db.get_recent_records(days, info_type=info_type)


@infoRouter.get(
    '/daily_usage',
    response_model=list[elec_schema.PeriodUsageInfoOut],
    tags=['Statistics'], )
async def get_daily_usage(
        days: Annotated[int, Query(ge=1)] = 7,
        recent_on_top: Annotated[bool, Query()] = True,
):
    """
    Parameters:

    - ``days``: The number of days you want to calculate usage statistics. Back starting from today.
    - ``recent_on_top``: If ``true``, then the day closest to today will at the first place of the return list.
    """
    return await provider_db.daily_usage_list(days=days, recent_on_top=recent_on_top)


@infoRouter.get(
    '/period_usage',
    response_model=list[elec_schema.PeriodUsageInfoOut],
    tags=['Statistics'],
)
async def get_period_usage(
        period: gene_schema.PeriodUnit,
        period_count: int,
        recent_on_top: bool = True,
):
    return await provider_db.period_usage_list(
        period=period,
        period_count=period_count,
        recent_on_top=recent_on_top,
    )
