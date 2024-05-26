from pydantic import BaseModel


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
