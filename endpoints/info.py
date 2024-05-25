import time

from fastapi import APIRouter

from schema.electric import Statistics, BalanceRecord
from provider.database import add_record, get_record_count
from provider import database as provider_db
from schema.electric import BalanceRecord
from schema import electric as elec_schema
from schema.sql import PaginationConfig

# Router for info
# Notice that this router actually do NOT add any prefix
infoRouter = APIRouter()


@infoRouter.get('/statistics', response_model=Statistics)
def get_statistic():
    return {
        'timestamp': time.time(),
        'total_last_day': 3.54,
        'total_last_7_days': 10.85,
        'record_last_7_days': []
    }


@infoRouter.post('/add_record', tags=['Record'])
async def add_new_record(new_record: BalanceRecord, use_current_timestamp: bool = False):
    # Override timestamp if needed
    if use_current_timestamp:
        new_record.timestamp = time.time()
    await add_record(new_record)


@infoRouter.get('/record_count', response_model=elec_schema.CountInfoOut, tags=['Record'])
async def record_count():
    return await get_record_count()


@infoRouter.post(
    '/records',
    response_model=list[BalanceRecord],
    tags=['Record'])
async def get_record_list(pagination: PaginationConfig):
    return await provider_db.get_records(pagination)
