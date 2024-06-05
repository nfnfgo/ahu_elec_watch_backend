import math
import time
import datetime
import functools

from pydantic import BaseModel
from loguru import logger

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from sqlalchemy.sql import and_, or_
from sqlalchemy import exc as sqlexc

import config.general
from exception import error as exc

from config import sql

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
        timestamp=record_info.timestamp,
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
            print(timestamp_7_day_ago)
            stmt_last_7 = select(
                func.count(SQLRecord.timestamp)).where(SQLRecord.timestamp > timestamp_7_day_ago)
            print(stmt_last_7)

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
    If no timestamp satisfied, return the oldest one, if no record, raise no_result error
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


def convert_balance_list_to_usage_list(
        record_list: list[BalanceRecord | SQLRecord],
        # point_spreading: bool = True,
        # smoothing: bool = True,
        # per_hour_usage: bool = True,
        # point_merge_ratio: int | None = None,
        usage_convert_config: elec_schema.UsageConvertConfig,

) -> list[BalanceRecord | SQLRecord]:
    """
    Convert the balance info to usage info of a record list by doing difference calculation.

    Parameters:

    - ``record_list`` List of records. Could be ``BalanceRecord`` or ``SQLRecord``.
    - ``usage_convert_config``: Configs when converting record list. Check out `UsageConvertConfig` for more info.

    Notice the timestamp of passed ``record_list`` must be ascending.

    Noice when passing SQLRecord type object list, **make sure that mutating these object in list
    will NOT cause the data change in database**. For example you shouldn't passing object that
    got while using ``session.begin()`` context manager.

    Notice, the process will be executed as the same order as the one they in config model.



    Returns:

    List with element type of `BalanceRecord` or `SQLRecord`.
    """
    # ensure config received
    if usage_convert_config is None:
        raise exc.ParamError(
            'usage_convert_config',
            'Must provide convert config to usage convert function', )

    size = len(record_list)
    # Don't deal with empty list
    if size == 0:
        return []

    # iterate from end to start to update the balance to usage.
    # notice no negative usage allowed here. Which will be forcefully pull up to 0
    for i in range(size - 1, 0, -1):
        record_list[i].light_balance = max(0.0, record_list[i - 1].light_balance - record_list[i].light_balance)
        record_list[i].ac_balance = max(0.0, record_list[i - 1].ac_balance - record_list[i].ac_balance)

    # set the first usage record data to zero.
    # for more info about why doing this, check out docs/usage_calc.md
    record_list[0].ac_balance = 0
    record_list[0].light_balance = 0

    if usage_convert_config.spreading:
        record_list = usage_list_point_spreading(record_list=record_list)

    if usage_convert_config.smoothing:
        record_list = usage_list_smoothing(record_list=record_list)

    if usage_convert_config.per_hour_usage:
        factor: float = config.general.BACKEND_CATCH_TIME_DURATION_MIN / 60
        factor = 1 / factor
        for i in range(len(record_list)):
            record_list[i].light_balance = record_list[i].light_balance * factor
            record_list[i].ac_balance = record_list[i].ac_balance * factor

    if usage_convert_config.use_smart_merge:
        # here None merge_ratio param is allowed, which will cause smart_point_merge() to find out smart ratio automatically.
        record_list = smart_points_merge(record_list=record_list, merge_ratio=usage_convert_config.merge_ratio)

    return record_list


def usage_list_point_spreading(
        record_list: list[SQLRecord | BalanceRecord]
) -> list[SQLRecord | BalanceRecord]:
    """
    Implement data point spreading on the receiving usage record list then returns it.

    Parameters:

    - ``record_list`` List of **usage** records. Require ascending timestamp.

    Notice if you passing a ``SQLRecord`` list, then this function may mutating the value inside database if some SQLRecord
    instance are in SQLAlchemy Transaction Context.

    For more info about *Data Point Spreading*, check out ``docs/usage_calc.md`` Data Point Spreading part.
    """
    list_len = len(record_list)
    # only list with more than two elements could perform data spreading
    if list_len < 2:
        return record_list

    max_dis: int = config.general.POINT_SPREADING_DIS_LIMIT_MIN * 60

    # using a new temporary list to store the newly added point
    # Here use a new list because we can not mutate the list while iterating it.
    added_record_list: list[BalanceRecord] = []

    for cur_idx in range(1, list_len):
        # calculate timestamp distance
        timestamp_diff: int = int(record_list[cur_idx].timestamp - record_list[cur_idx - 1].timestamp)
        # no need for spreading
        if timestamp_diff <= max_dis:
            continue

        # calculate point count and new value
        new_point_count: int = (timestamp_diff - 1) // max_dis
        new_value_light: float = round(record_list[cur_idx].light_balance / (new_point_count + 1), 2)
        new_value_ac: float = round(record_list[cur_idx].ac_balance / (new_point_count + 1), 2)

        # update data of the record2
        record_list[cur_idx].light_balance = new_value_light
        record_list[cur_idx].ac_balance = new_value_ac

        # adding new point to waiting list
        current_timestamp = record_list[cur_idx].timestamp
        for back_idx in range(1, new_point_count + 1):
            # calc new point timestamp by offset
            new_timestamp = current_timestamp - back_idx * max_dis
            # add point
            added_record_list.append(BalanceRecord(
                timestamp=new_timestamp,
                light_balance=new_value_light,
                ac_balance=new_value_ac,
            ))

    # merge two list and sort by timestamp ascending
    record_list.extend(added_record_list)
    record_list.sort(key=lambda x: x.timestamp)

    return record_list


def usage_list_smoothing(record_list: list[SQLRecord | BalanceRecord]) -> list[SQLRecord | BalanceRecord]:
    """
    Smoothing a usage record list.

    - ``record_list`` must be **ascending in timestamp**.

    Notice, this function **will NOT mutate the original list object**.

    Returns:

    - A new list of ``BalanceRecord`` list (when received list len >= 3)
    - Original list object (when received list len <3)
    """
    list_len = len(record_list)
    if list_len < 3:
        return record_list

    ratio_list: list[float] = [0.1, 0.7, 0.2]

    # here we need to use a new record list to store the smoothed point
    # because we can NOT mutate the info while iterating throw it.
    new_record_list: list[SQLRecord | BalanceRecord] = []

    new_record_list.append(BalanceRecord(
        timestamp=record_list[0].timestamp,
        light_balance=record_list[0].light_balance,
        ac_balance=record_list[0].ac_balance,
    ))

    for cur_idx in range(1, list_len - 2):
        # create new record in the new list
        new_record_list.append(BalanceRecord())

        # write info into the new record
        new_record_list[cur_idx].light_balance = (
                record_list[cur_idx - 1].light_balance * ratio_list[0] +
                record_list[cur_idx].light_balance * ratio_list[1] +
                record_list[cur_idx + 1].light_balance * ratio_list[2]
        )

        new_record_list[cur_idx].ac_balance = (
                record_list[cur_idx - 1].ac_balance * ratio_list[0] +
                record_list[cur_idx].ac_balance * ratio_list[1] +
                record_list[cur_idx + 1].ac_balance * ratio_list[2]
        )

        new_record_list[cur_idx].timestamp = record_list[cur_idx].timestamp

    new_record_list.append(BalanceRecord(
        timestamp=record_list[-1].timestamp,
        light_balance=record_list[-1].light_balance,
        ac_balance=record_list[-1].ac_balance,
    ))

    return new_record_list


def smart_points_merge(
        record_list: list[SQLRecord | BalanceRecord],
        merge_ratio: int | None,
):
    """
    Implement smart usage point merge on received usage record list.

    Parameters:

    - ``record_list``: The original `record_list`, required ascending timestamp.
    - ``merge_ratio``: How many original points will be merged into a new single point. positive ``int`` value

    Returns:

    - New `BalanceRecord` list (when received list len >= `merge_ratio`)
    - Original list. When `ratio == 1`, or list len < `merge_ratio`
    """
    # use auto calculated default ratio
    if merge_ratio is None:
        # calculate default merge ratio use day as density standard
        time_range = record_list[-1].timestamp - record_list[0].timestamp
        merge_ratio = math.floor(time_range / (24 * 60 * 60))

    merge_ratio = int(merge_ratio)
    merge_ratio = max(1, merge_ratio)

    # the case we directly return original list.
    list_len = len(record_list)
    if merge_ratio == 1 or list_len < merge_ratio:
        return record_list

    new_record_list: list[BalanceRecord] = []

    for cur_idx in range(0, list_len, merge_ratio):
        max_offset: int = min(merge_ratio, list_len - cur_idx)

        sum_ac: float = 0
        sum_light: float = 0
        loop_count: int = 0

        for i in range(0, max_offset):
            sum_ac += record_list[cur_idx + i].ac_balance
            sum_light += record_list[cur_idx + i].light_balance
            loop_count += 1

        avg_ac = sum_ac / loop_count
        avg_light = sum_light / loop_count
        last_timestamp = record_list[cur_idx + max_offset - 1].timestamp

        new_record_list.append(BalanceRecord(
            timestamp=last_timestamp,
            light_balance=avg_light,
            ac_balance=avg_ac,
        ))

    return new_record_list


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


def convert_to_model_record_list(record_list: list[BalanceRecord | SQLRecord]) -> list[BalanceRecord]:
    """
    Convert a mixed ``list[BalanceRecord | SQLRecord]`` to pure ``list[BalanceRecord]``

    Converting to pure Pydantic Model list could promise all data is well validate including floating point rounding etc.
    """
    new_list: list[BalanceRecord] = []
    for record in record_list:
        new_list.append(BalanceRecord(
            timestamp=record.timestamp,
            light_balance=record.light_balance,
            ac_balance=record.ac_balance,
        ))
    return new_list


async def get_records_by_time_range(
        start_time: int,
        end_time: int | None,
        usage_convert_config: elec_schema.UsageConvertConfig | None,
) -> list[BalanceRecord | SQLRecord]:
    """
    Get all records during a specified time range.

    Parameter:

    - ``start_time``: Start of the time range. `int` UNIX timestamp.
    - ``end_time``: End of the time range. `int` UNIX timestamp. If `None`, default to current timestamp.
    - ``usage_convert_config``: If NOT `None`, use this config to convert balance record list to usage list.

    Notice: ``end_time`` must be greater than or equal to ``start_time``.
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
    ).order_by(SQLRecord.timestamp.asc())

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

        if usage_convert_config is not None:
            record_list: list[SQLRecord | BalanceRecord] = record_list  # type anno
            record_list = convert_balance_list_to_usage_list(
                record_list=record_list,
                usage_convert_config=usage_convert_config,
            )

        return convert_to_model_record_list(record_list=record_list)
