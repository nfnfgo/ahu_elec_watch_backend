import asyncio
from loguru import logger
from aiohttp import ClientSession

from provider import ahu
from provider import database

from schema.electric import BalanceRecord


async def main():
    ahu.aiohttp_session = ClientSession(base_url='https://ycard.ahu.edu.cn')
    record_dict = await ahu.get_record()
    logger.info('Record caught from AHU:', record_dict)

    try:
        record_ins = BalanceRecord(**record_dict)
        await database.add_record(record_ins)
    except Exception as e:
        logger.error('Failed to add record info into database')
        logger.exception(e)

    await ahu.aiohttp_session.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except RuntimeError as re:
        logger.success('Task accomplished')