from pydantic import BaseModel, Field


class AHUHeaderInfo(BaseModel):
    """
    Class used to pass and receive AHU header info from user.

    This class must have an explicit custom ``from_dict()`` and ``to_dict()`` method
    since the key name in header is different from the field name in this class.
    """
    # Original key in header is ``Authorization``
    authorization: str
    # Original key in header is ``synjones-auth``
    synjones_auth: str

    @classmethod
    def from_dict(cls, info_dict: dict):
        return cls(
            authorization=info_dict['Authorization'],
            synjones_auth=info_dict['synjones-auth'],
        )

    def to_dict(self):
        return {
            'Authorization': self.authorization,
            'synjones-auth': self.synjones_auth,
        }
