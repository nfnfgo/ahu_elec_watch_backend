import time
import functools

from pydantic import BaseModel
from loguru import logger

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from sqlalchemy import exc as sqlexc

from exception import error as exc

from config import sql

from schema.electric import SQLRecord, BalanceRecord, CountInfoOut
from schema import sql as sql_schema
from schema import electric as elec_schema

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


def run_with_session(func, session_maker: async_sessionmaker = session_maker):
    """
    Let the decorated function runs in a session produced by session maker
    :param func: An async function
    :param session_maker: You can assign the ``async_sessionmaker`` if you want.
    """

    @functools.wraps()
    async def wrapper(*args, **kwargs):
        async with session_maker() as session:
            async with session.begin():
                return await func()

    return wrapper


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
        async with session.begin():
            try:
                res = await session.scalars(stmt)
            except exc.NoSuchColumnError as e:
                res = []
            record_list: list[BalanceRecord] = res.all()
            return record_list
    pass


async def find_record_timestamp_days_ago(days: int = 7) -> int:
    """
    Find out and return an `int` timestamp that closest to a specified number of days ago.
    :param days: How many days ago you want to find the timestamp closest to.
    :return: The timestamp. If no timestamp satisfied, return the oldest one, if no record, raise no_result error
    """
    ideal_timestamp: int = int(time.time()) - days * 24 * 60 * 60

    stmt_find_after_ideal_timestamp = (select(func.min(SQLRecord.timestamp))
                                       .where(SQLRecord.timestamp > ideal_timestamp)
                                       .order_by(SQLRecord.timestamp))

    stmt_latest_timestamp = (select(SQLRecord.timestamp).order_by(SQLRecord.timestamp.desc()).limit(limit=1))

    logger.debug('Statement to find out recent day timestamp:', stmt_find_after_ideal_timestamp)

    async with session_maker() as session:
        async with session.begin():
            timestamp = -1
            try:
                res = await session.scalars(stmt_find_after_ideal_timestamp)
                timestamp = res.one()
            except sqlexc.NoSuchColumnError as e:
                try:
                    res = await session.scalars(stmt_latest_timestamp)
                    timestamp = res.one()
                except sqlexc.NoSuchColumnError as e:
                    raise exc.NoResultError('Could not found record close to a specified time')
            return timestamp


def calculate_usage(record_list: list[BalanceRecord]) -> dict[str, int]:
    """
    Calculate the light and ac uaages based on a record list.

    Returns A dict with both light and ac usage::

        {
            light_usage: int,
            ac_usage: int,
        }


    :param record_list: List of records. Requires ascending timestamp
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


def convert_balance_list_to_usage_list(record_list: list[BalanceRecord | SQLRecord]) -> list[BalanceRecord | SQLRecord]:
    size = len(record_list)
    # Don't deal with empty list
    if size == 0:
        return []

    # iterate from end to start to update the balance to usage.
    # notice no negative usage allowed here. Which will be forcefully pull up to 0
    for i in range(size, 0, -1):
        record_list[i].light_balance = max(0.0, record_list[i - 1].light_balance - record_list[i].light_balance)
        record_list[i].ac_balance = max(0.0, record_list[i - 1].ac_balance - record_list[i].ac_balance)

    return record_list


async def get_recent_records(
        days: int,
        type: elec_schema.RecordDataType,
) -> list[SQLRecord]:
    """
    Get all the records in recent days.

    Notes that the list return is asc by timestamp, means old record in the begining.

    :param days: The days you want to get records starts from.
    :param type: The return type of the data list. Check `RecordDataType` for more info.
    :return: A list of BalanceRecord objects. If no result, return empty list.
    """
    timestamp_day_ago: int = int(time.time()) - days * 24 * 60 * 60
    stmt = select(SQLRecord).where(SQLRecord.timestamp >= timestamp_day_ago).order_by(SQLRecord.timestamp.asc())
    async with session_maker() as session:
        async with session.begin():
            try:
                res = await session.scalars(stmt)
                sql_obj_list: list[SQLRecord] = res.all()
                if type == elec_schema.RecordDataType.usage:
                    return convert_balance_list_to_usage_list(sql_obj_list)
                return sql_obj_list
            except sqlexc.NoSuchColumnError as e:
                return []
