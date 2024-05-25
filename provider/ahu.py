import time

from aiohttp import ClientSession
import re
from schema.electric import BalanceRecord
from config import dorm

aiohttp_session: ClientSession | None = ClientSession(base_url='https://ycard.ahu.edu.cn')


async def init_client_session(force_create: bool = False):
    global aiohttp_session
    if aiohttp_session is None or force_create:
        aiohttp_session = ClientSession(base_url='https://ycard.ahu.edu.cn')
    return aiohttp_session


def extract_balance(json):
    s = json['map']['showData']['信息']
    return float(re.sub(r'\D', '', s)) / 100


async def get_record() -> dict:
    """
    Get current record from AHU official website

    Return a dict with info::

        {
            timestamp: int,
            ac_balance: float,
            light_balance: float,
        }
    """
    light_balance: float = 0
    ac_balance: float = 0
    async with aiohttp_session.post(
            url='/charge/feeitem/getThirdData',
            data=dorm.DORM_LIGHT_INFO_DICT,
            headers=dorm.DORM_REQ_HEADER_DICT,
    ) as res:
        json = await res.json()
        light_balance = extract_balance(json)

    async with aiohttp_session.post(
            url='/charge/feeitem/getThirdData',
            data=dorm.DORM_AC_INFO_DICT,
            headers=dorm.DORM_REQ_HEADER_DICT,
    ) as res:
        json = await res.json()
        ac_balance = extract_balance(json)
    return {
        'timestamp': time.time(),
        'light_balance': light_balance,
        'ac_balance': ac_balance,
    }
