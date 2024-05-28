import time

import jwt
from pydantic import BaseModel

from config import auth as auth_conf
from exception import error as exc


class TokenData(BaseModel):
    role_name: str
    created_at: int
    disabled: bool = False

    @classmethod
    def from_jwt(self, jwt_str: str) -> 'TokenData':
        """
        Return a ``TokenData`` instance based on a JWT string
        """
        info_dict = jwt.decode(
            key=auth_conf.PYJWT_SECRET_KEY,
            jwt=jwt_str,
            algorithms=auth_conf.PYJWT_ALGORITHM,
        )
        return TokenData(**info_dict)

    def to_jwt(self) -> str:
        return jwt.encode(
            key=auth_conf.PYJWT_SECRET_KEY,
            payload=self.model_dump(),
            algorithm=auth_conf.PYJWT_ALGORITHM,
        )

    def try_verify(self, role_list: list[str]) -> True:
        """
        Try to verify this token by providing a list of allowed role

        Will raise ``TokenError`` when error occurred. If success, return `true`.

        :param role_list: The list of allowed roles
        """
        # check if expired
        current_time = time.time()
        valid_until = self.created_at + auth_conf.TOKEN_EXPIRES_DELTA_HOURS * 3600
        if current_time > valid_until:
            raise exc.TokenError(expired=True)

        # check if role matched
        if self.role_name not in role_list:
            raise exc.TokenError(role_not_match=True)

        return True
