import time

from loguru import logger

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from exception import error as exc

from config import sql
from provider.algorithms import (
    convert_balance_list_to_usage_list,
    convert_to_model_record_list
)

from schema.electric import SQLRecord, BalanceRecord, CountInfoOut, PeriodUsageInfoOut
from schema import sql as sql_schema
from schema import electric as elec_schema
from schema import general as general_schema

_engine = create_async_engine(
    f"mysql+aiomysql://"
    f"{sql.DB_USERNAME}:{sql.DB_PASSWORD}"
    f"@{sql.DB_HOST}/{sql.DB_NAME}"
)

# async version sessionmaker
# call init_sessionmaker() before use this instance
session_maker: async_sessionmaker | None = async_sessionmaker(_engine, expire_on_commit=False)


async def init_sessionmaker(force_create: bool = False) -> async_sessionmaker:
    """
    (Async) Tool function to initialize the session maker if it's not ready.
    :return: None
    """
    global session_maker
    if (session_maker is None) or force_create:
        logger.info('Session maker initializing...')
        session_maker = async_sessionmaker(_engine, expire_on_commit=False)
        logger.success('Session maker initialized')
    else:
        logger.debug('Session maker already ready')
    return session_maker


# deprecated
# def run_with_session(func, session_maker: async_sessionmaker = session_maker):
#     """
#     Let the decorated function runs in a session produced by session maker
#     :param func: An async function
#     :param session_maker: You can assign the ``async_sessionmaker`` if you want.
#     """
#
#     @functools.wraps()
#     async def wrapper(*args, **kwargs):
#         async with session_maker() as session:
#             async with session.begin():
#                 return await func()
#
#     return wrapper


async def add_record(record_info: BalanceRecord):
    """
    Add a record to the database
    :param record_info: dict that contain light and ac balance.
    :return:
    """
    new_rec = SQLRecord(
        timestamp=int(record_info.timestamp),
        light_balance=record_info.light_balance,
        ac_balance=record_info.ac_balance,
    )

    async with session_maker() as session:
        async with session.begin():
            session.add(new_rec)


async def get_record_count() -> CountInfoOut:
    """
    Get count of records in the database
    """
    async with session_maker() as session:
        async with session.begin():
            # statement
            stmt = select(func.count(SQLRecord.timestamp)).distinct()
            timestamp_7_day_ago = time.time() - 7 * 24 * 60 * 60
            timestamp_7_day_ago = int(timestamp_7_day_ago)

            stmt_last_7 = select(
                func.count(SQLRecord.timestamp)).where(SQLRecord.timestamp > timestamp_7_day_ago)

            # retrive data
            try:
                res = (await session.scalars(stmt)).one_or_none()
            except sqlexc.NoSuchColumnError as e:
                res = 0
            try:
                res_last_7 = (await session.scalars(stmt_last_7)).one_or_none()
            except sqlexc.NoSuchColumnError as e:
                res_last_7 = 0
            return CountInfoOut(total=res, last_7_days=res_last_7)


async def get_records(pagination: sql_schema.PaginationConfig) -> list[BalanceRecord]:
    stmt = select(SQLRecord).order_by(SQLRecord.timestamp.desc())
    stmt = pagination.use_on(stmt)
    async with session_maker() as session:
        try:
            res = await session.scalars(stmt)
        except sqlexc.NoSuchColumnError as e:
            res = []
        record_list: list[BalanceRecord] = res.all()
        return record_list
    pass


async def find_record_timestamp_days_ago(days: int = 7) -> int:
    """
    Find out and return an `int` timestamp that closest to a specified number of days ago.

    Parameters:

    - ``days`` How many days ago you want to find the timestamp closest to.

    Notice here days **does NOT mean natural day** but means 24 hours.

    Returns:

    The timestamp later than that day back and closest to that day.
    If no timestamp satisfied, return the oldest one, if no record, raise ``no_result`` error
    """
    ideal_timestamp: int = int(time.time()) - days * 24 * 60 * 60

    stmt_find_after_ideal_timestamp = (select(func.min(SQLRecord.timestamp))
                                       .where(SQLRecord.timestamp > ideal_timestamp)
                                       .order_by(SQLRecord.timestamp))

    stmt_latest_timestamp = (select(SQLRecord.timestamp).order_by(SQLRecord.timestamp.desc()).limit(limit=1))

    async with session_maker() as session:
        async with session.begin():
            timestamp = -1
            try:
                res = await session.scalars(stmt_find_after_ideal_timestamp)
                timestamp = res.one()
                if timestamp is None:
                    raise sqlexc.NoSuchColumnError()
            except sqlexc.NoSuchColumnError as e:
                try:
                    res = await session.scalars(stmt_latest_timestamp)
                    timestamp = res.one()
                except sqlexc.NoSuchColumnError as e:
                    raise exc.NoResultError('Could not found record close to a specified time')
            return timestamp


def calculate_usage(
        record_list: list[BalanceRecord],
        result_rounded: bool = True,
) -> dict[str, int]:
    """
    Calculate the light and ac uaages based on a record list.

    Returns A dict with both light and ac usage::

        {
            light_usage: int,
            ac_usage: int,
        }


    Parameters:
    - ``record_list``: List of records. Requires ascending timestamp.
    - ``result_rounded``: If `true`, result will be rounded to two decimal places.
    """
    light_usage = 0
    ac_usage = 0
    size = len(record_list)

    for i in range(1, size):
        light_diff = record_list[i].light_balance - record_list[i - 1].light_balance
        ac_diff = record_list[i].ac_balance - record_list[i - 1].ac_balance

        light_diff = min(light_diff, 0)
        ac_diff = min(ac_diff, 0)

        light_usage -= light_diff
        ac_usage -= ac_diff

    if result_rounded:
        light_usage = round(light_usage, 2)
        ac_usage = round(ac_usage, 2)

    return {
        'light_usage': light_usage,
        'ac_usage': ac_usage,
    }


async def get_statistics() -> elec_schema.Statistics:
    try:
        timestamp_day_ago: int = await find_record_timestamp_days_ago(1)
        timestamp_7_days_ago: int = await find_record_timestamp_days_ago(7)
    except exc.NoResultError as e:
        raise exc.NoResultError(
            'No record found. Statistics only available when there is at least one record in database'
        )

    usage_day: dict = {}
    usage_week: dict = {}

    async with session_maker() as session:
        async with session.begin():
            # retrieve and calc daily usage
            res = await session.scalars(
                select(SQLRecord).where(SQLRecord.timestamp > timestamp_day_ago).order_by(SQLRecord.timestamp.asc())
            )
            record_list: list[BalanceRecord] = res.all()
            usage_day = calculate_usage(record_list)

            # retrieve and calc weekly usage
            res = await session.scalars(
                select(SQLRecord).where(SQLRecord.timestamp > timestamp_7_days_ago).order_by(SQLRecord.timestamp.asc())
            )
            record_list: list[BalanceRecord] = res.all()
            usage_week = calculate_usage(record_list)

    return elec_schema.Statistics(
        timestamp=time.time(),
        light_total_last_day=usage_day['light_usage'],
        ac_total_last_day=usage_day['ac_usage'],
        light_total_last_week=usage_week['light_usage'],
        ac_total_last_week=usage_week['ac_usage'],
    )


async def get_recent_records(
        days: int,
        usage_convert_config: elec_schema.UsageConvertConfig,
) -> list[SQLRecord]:
    """
    Get all the records in recent days.

    - ``days`` The days you want to get records starts from.
    - ``usage_convert_config`` If not `None`, convert the balance list to usage list using this config.

    Returns:

    Returns A list of BalanceRecord objects. If no result, return empty list.
    Notes that the list return is asc by timestamp, means old record in the beginning.
    """
    timestamp_day_ago: int = int(time.time()) - days * 24 * 60 * 60
    return await get_records_by_time_range(start_time=timestamp_day_ago,
                                           end_time=None,
                                           usage_convert_config=usage_convert_config)
    # stmt = select(SQLRecord).where(SQLRecord.timestamp >= timestamp_day_ago).order_by(SQLRecord.timestamp.asc())
    # async with session_maker() as session:
    #     try:
    #         res = await session.scalars(stmt)
    #         sql_obj_list: list[SQLRecord] = res.all()
    #
    #         ratio: int | None = None
    #         if use_smart_merge:
    #             ratio = days
    #
    #         # convert to usage list if required
    #         if info_type == elec_schema.RecordDataType.usage:
    #             return convert_balance_list_to_usage_list(
    #                 sql_obj_list,
    #                 per_hour_usage=per_hour_usage,
    #                 point_spreading=point_spreading,
    #                 smoothing=smoothing,
    #                 point_merge_ratio=ratio,
    #             )
    #
    #         return sql_obj_list
    #     except sqlexc.NoSuchColumnError as e:
    #         return []


# deprecated
# def get_timestamp_of_today_start() -> int:
#     """
#     Return the timestamp of today start, that is today-0:00AM
#     :return: ``int`` type timestamp
#     """
#     today_current = datetime.date.today()
#     time_min = datetime.time.min
#
#     today_start = datetime.datetime.combine(today_current, time_min)
#
#     return int(today_start.timestamp())


async def daily_usage_list(
        days: int,
        recent_on_top: bool,
) -> list[elec_schema.PeriodUsageInfoOut]:
    """
    Returns a list contains the usage statistics by days.


    :param days: The number of days you want to calculate usage statistics. Back starting from today.
    :param recent_on_top: If ``true``, then the day closest to today will at the first place of the return list.
    :return: A list of ``DailyUsageInfo`` objects.
    """

    logger.warning('This method is deprecated, use period_usage_list instead.')

    return await period_usage_list(
        period=general_schema.PeriodUnit.day,
        period_count=days,
        recent_on_top=recent_on_top,
    )


async def period_usage_list(
        period: general_schema.PeriodUnit,
        period_count: int,
        recent_on_top: bool = True):
    """
    Get usage statistics list with specified period as time duration unit.

    Parameter:

    - ``period``: The period unit. Check `PeriodUnit` enum class for more info.
    - ``period_count``: How many periods of usage should be in the result list.
    """
    current_timestamp: int = int(time.time())
    period_start_timestamp: int = general_schema.PeriodUnit.get_current_period_start(period)

    # list store all result items
    result_list: list[elec_schema.PeriodUsageInfoOut] = []

    # store the current start time in this loop
    cur_start_time: int = period_start_timestamp
    cur_end_time: int = current_timestamp
    async with session_maker() as session:
        for back_idx in range(0, period_count + 1):
            if back_idx == 0:
                cur_end_time = current_timestamp

            # construct statement and execute it
            stmt = select(SQLRecord).where(
                and_(
                    SQLRecord.timestamp >= cur_start_time,
                    SQLRecord.timestamp <= cur_end_time,
                )
            )
            try:
                res = await session.scalars(stmt)
                record_list = res.all()
                if record_list is None:
                    raise sqlexc.NoSuchColumnError()
            except sqlexc.NoSuchColumnError as e:
                record_list = []

            # calculate the usage
            usage_dict = calculate_usage(record_list=record_list)
            result_list.append(PeriodUsageInfoOut(
                start_time=cur_start_time,
                end_time=cur_end_time,
                ac_usage=usage_dict['ac_usage'],
                light_usage=usage_dict['light_usage'],
            ))

            # update start and end time of next loop
            cur_start_time = general_schema.PeriodUnit.get_previous_period_start(period, cur_start_time)
            cur_end_time = general_schema.PeriodUnit.get_period_end(period, cur_start_time)

    if not recent_on_top:
        result_list.reverse()

    return result_list


async def get_records_by_time_range(
        start_time: int,
        end_time: int | None,
        usage_convert_config: elec_schema.UsageConvertConfig | None,
) -> list[BalanceRecord]:
    """
    Get all records during a specified time range.

    Parameters:

    - ``start_time``: Start of the time range. `int` UNIX timestamp.
    - ``end_time``: End of the time range. `int` UNIX timestamp. If `None`, default to current timestamp.
    - ``usage_convert_config``: If NOT `None`, use this config to convert balance record list to usage list.

    Return:

    - A list of ``BalanceRecord`` with ascending timestamp.

    Notice:

    - ``end_time`` must be greater than or equal to ``start_time``.
    - If need to convert to usage list (``usage_convert_config`` is not None), then the input and output should also
      follow the standard of the convert function.
    """
    # use default end time if None
    if end_time is None:
        end_time = int(time.time())

    start_time = int(start_time)
    end_time = int(end_time)

    # end_time bigger than start_time
    if end_time < start_time:
        raise exc.ParamError(
            'end_time',
            'end_time should satisfy end_time >= start_time')

    # time should be in the past
    current_time = int(time.time())
    if end_time > current_time:
        raise exc.ParamError('end_time', 'end_time should be a time that in the past.')

    # construct statement
    stmt = select(SQLRecord).where(
        and_(
            SQLRecord.timestamp >= start_time,
            SQLRecord.timestamp <= end_time,
        )
    ).order_by(SQLRecord.timestamp.asc())  # ensure timestamps are ascending

    async with session_maker() as session:
        try:
            res = await session.scalars(stmt)
            record_list = res.all()
            if record_list is None:
                raise sqlexc.NoSuchColumnError()
        except sqlexc.NoSuchColumnError as e:
            record_list = []
            # if the list is empty, no need to do convert anymore
            return record_list

        # if config not None, convert to usage list
        if usage_convert_config is not None:
            record_list: list[SQLRecord | BalanceRecord] = record_list  # type anno
            record_list = convert_balance_list_to_usage_list(
                record_list=record_list,
                usage_convert_config=usage_convert_config,
            )

        return convert_to_model_record_list(record_list=record_list)


async def delete_records_by_time_range(start: int, end: int, dry_run: bool = False) -> int:
    """
    Remove records from database with specific time range [start, end] (Notice that end time included in range)

    Params:

    - ``start`` UNIX timestamp of the start time range.
    - ``end`` UNIX timestamp of the end time range.
    - ``dry_run`` If `True`, will only test the affected records count, and will NOT delete the records.

    Returns:

    - Total count of records deleted.
    """

    # legal check
    if start > end:
        raise exc.ParamError(
            'end',
            'End time must be greater than start time.'
        )

    # construct statement
    stmt = select(SQLRecord).where(
        and_(
            SQLRecord.timestamp >= start,
            SQLRecord.timestamp <= end,
        ),
    )

    affected: int = 0

    async with session_maker() as session:
        async with session.begin():
            res = (await session.scalars(stmt)).all()
            affected = len(res)

            # if dry run, return
            if dry_run:
                return affected

            # delete records
            for record in res:
                await session.delete(record)

    return affected


async def get_statistics_by_time_range(start_time: int, end_time: int):
    """
    Get statistics info of a specific time range.

    Parameters:

    - ``start`` UNIX timestamp of the start time range.
    - ``end`` UNIX timestamp of the end time range.
    """

    # get usage list
    usage_list: list[BalanceRecord] = await get_records_by_time_range(
        start_time, end_time,
        usage_convert_config=elec_schema.UsageConvertConfig(
            spreading=True,
            use_smart_merge=True,
            merge_ratio=None,
            smoothing=False,
            per_hour_usage=False,
            remove_first_point=True,
        ))

    # calculate total usage
    total_light: float = 0
    total_ac: float = 0
    for usage_item in usage_list:
        total_light += usage_item.light_balance
        total_ac += usage_item.ac_balance

    # calculate hour distance
    hour_distance: int = int((usage_list[-1].timestamp - usage_list[0].timestamp) / 3600)
