import time
from enum import Enum
from typing import Annotated
from pydantic import BaseModel

import jwt

from fastapi import APIRouter, Query, Depends, Request, Response
from fastapi.responses import JSONResponse

from config.auth import RoleInfo
from endpoints import deps

from provider.database import add_record, get_record_count
from provider import database as provider_db

from schema.electric import BalanceRecord
from schema import electric as elec_schema
from schema.sql import PaginationConfig
from schema.electric import Statistics, BalanceRecord

from exception import error as exc

from config import auth as auth_conf
from exception import error as exc

from schema.auth import TokenData

auth_router = APIRouter()


def auth_and_gen_jwt(role_need_to_auth: auth_conf.RoleInfo) -> str:
    """
    Try to authenticate this user with input credentials.
    :param role_need_to_auth: The auth credential.
    :return: The encoded jwt token for this user.
    """
    # loop the valid role to check
    for valid_role in auth_conf.ROLE_LIST:

        # matched, auth succeed
        if valid_role.auth(role_need_to_auth):
            # create token info for this user
            token_data = TokenData(
                role_name=valid_role.name,
                created_at=int(time.time()),
                disabled=False,
            )

            # return encoded jwt
            return token_data.to_jwt()

        # name matched, password incorrect
        if role_need_to_auth.name == valid_role.name:
            raise exc.AuthError(role=role_need_to_auth, has_match=True)

    # no role matched
    raise exc.AuthError(role=role_need_to_auth)


def require_role(
        role_list: list[str],
):
    """
    A dependency function generator used to generate a dependency function used by FastAPI to
    require a certain role.

    The generated dependency function will return `True` if verify passed. Else raise ``TokenError``.

    :param role_list: A list of string represents the roles that could pass the verification.
    """

    def generated_role_requirement_func(
            req: Request
    ):
        jwt_str = req.cookies.get('session')
        if jwt_str is None:
            raise exc.TokenError(no_token=True)

        # convert jwt string to token data
        token_data = TokenData.from_jwt(jwt_str=jwt_str)
        token_data.try_verify(role_list)
        return token_data.role_name

    return generated_role_requirement_func


class LoginTokenOut(BaseModel):
    token: str


@auth_router.post('/login', response_model=LoginTokenOut)
async def login_into_account(
        token: Annotated[str, Depends(auth_and_gen_jwt)],
        resp: Response):
    """
    Authenticate the credentials then return jwt token string
    and write cookies.
    """
    resp.set_cookie(key='session', value=token)
    return LoginTokenOut(token=token)


@auth_router.get('/logout')
async def logout_account(resp: Response):
    resp.delete_cookie('session')
    return JSONResponse(
        status_code=200,
        content={'is_logged_out': True}
    )


@auth_router.post('/role_test')
async def role_require_test(test=Depends(require_role(['admin']))):
    return test
