import time
from enum import Enum
from typing import Annotated
from pydantic import BaseModel

import jwt

from fastapi import APIRouter, Query, Depends, Request, Response, Body

from config import dorm as dorm_config
from endpoints import auth as auth_endpoint
from schema import ahu as ahu_schema

ahu_router = APIRouter()


@ahu_router.get('/header_info', response_model=ahu_schema.AHUHeaderInfo)
async def get_ahu_header_info(role=Depends(auth_endpoint.require_role(['admin']))):
    return ahu_schema.AHUHeaderInfo.from_dict(dorm_config.get_ahu_header(force_load_from_file=True))


@ahu_router.post('/set_header_info', response_model=ahu_schema.AHUHeaderInfo)
async def set_ahu_header_info(
        url_str: str = Body(),
        role=Depends(auth_endpoint.require_role(['admin'])),
):
    dorm_config.update_ahu_header(url_str=url_str, clear_cache=True)
    return ahu_schema.AHUHeaderInfo.from_dict(dorm_config.get_ahu_header(force_load_from_file=True))
