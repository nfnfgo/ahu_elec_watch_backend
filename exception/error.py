from pydantic import BaseModel

from config.auth import RoleInfo


class BaseError(Exception):
    """
    Base error class for backend application
    """
    name: str
    message: str
    status: int

    def __init__(self, name: str, message: str, status: int = 403) -> None:
        super().__init__(message)
        self.message = message
        self.name = name
        self.status = status

    def to_pydantic_base_error(self):
        return BaseErrorOut.from_base_error(self)


class BaseErrorOut(BaseModel):
    """
    Class that used to convert BaseError to a pydantic class that could be passed to frontend through API.
    """
    name: str
    message: str
    status: int

    @classmethod
    def from_base_error(cls, e: BaseError):
        return cls(name=e.name, message=e.message, status=e.status)


class NoResultError(BaseError):
    """
    Raise when could not find any result satisfying condition from database.
    """

    def __init__(self, message: str = 'Could not found any result satisfying condition from database.') -> None:
        super().__init__(
            name='no_result',
            message=message,
            status=404,
        )


class AuthError(BaseError):
    """
    Raise when backend could not authorize user with given credentials.

    Check `__init__()` for more info.
    """

    def __init__(self, role: RoleInfo | None, has_match: bool = False):
        """
        Create an `AuthError` instance.

        :param role: RoleInfo instance used to generate error. Generally pass the roleInfo that user passed to backend.
        :param has_match: If `true`, means the role name has matched with a valid role, but password incorrect.
        """
        err_msg: str = 'User authentication failed, please check if you passed the correct role name and password'
        if role is not None:
            err_msg = f'Role info not valid. Role "{role.name}" is not a valid role in system'
        if has_match:
            err_msg = f'Password incorrect for role named {role.name}'
        super().__init__(name='auth_error', message=err_msg, status=401)  # return unauthorized response


class TokenError(BaseError):
    """
    Raise when error occurred while verifying token.

    Check out __init__() for more info.
    """

    def __init__(
            self,
            message: str | None = None,
            expired: bool | None = None,
            role_not_match: bool | None = None,
            no_token: bool | None = None,
    ) -> None:
        final_name = 'token_error'
        final_message = message
        """
        Create an `TokenError` instance.
        :param message:
        :param expired: If `true`, indicates the token is expired.
        :param role_not_match: If `true`, indicates the role are not match the requirements.
        """
        if message is None:
            message = 'Could not verify the user tokens'

        if expired:
            final_name = 'token_expired'
            message = 'Token expired, try login again to get a new token'

        if role_not_match:
            final_name = 'token_role_not_match'
            message = 'Current role are not match the requirements to perform this operation or access this resources'

        if no_token:
            final_name = 'token_required'
            message = 'Could not found a valid token, try login to an valid account'

        # only when message is None, then use presets, otherwise always use the original message passed.
        if final_message is None:
            final_message = message

        super().__init__(
            name=final_name,
            message=final_message,
            status=401
        )
