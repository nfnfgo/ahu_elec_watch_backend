import time

from pydantic import BaseModel
from loguru import logger

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from sqlalchemy import exc

from config import sql

from schema.electric import SQLRecord, BalanceRecord, CountInfoOut
from schema import sql as sql_schema

_engine = create_async_engine(
    f"mysql+aiomysql://"
    f"{sql.DB_USERNAME}:{sql.DB_PASSWORD}"
    f"@{sql.DB_HOST}/{sql.DB_NAME}"
)

# async version sessionmaker
session_maker = async_sessionmaker(_engine, expire_on_commit=False)


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
            except exc.NoSuchColumnError as e:
                res = 0
            try:
                res_last_7 = (await session.scalars(stmt_last_7)).one_or_none()
            except exc.NoSuchColumnError as e:
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
                logger.debug('No record found, return empty record list')
                res = []
            record_list: list[BalanceRecord] = res.all()
            return record_list
    pass
