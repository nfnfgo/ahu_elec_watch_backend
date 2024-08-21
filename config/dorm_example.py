import json
import re

from exception import error as exc

AHU_WEBSITE: str = 'https://ycard.ahu.edu.cn'

DORM_LIGHT_INFO_DICT = {
    "feeitemid": "YOUR_FEE_ITEM_ID_HERE",
    "type": "YOUR_AC_TYPE_HERE",
    "level": "YOUR_AC_LEVEL_HERE",
    "campus": "YOUR_CAMPUS_HERE",
    "building": "YOUR_BUILDING_HERE",
    "floor": "YOUR_FLOOR_HERE",
    "room": "YOUR_ROOM_HERE"
}

DORM_AC_INFO_DICT = {
    "feeitemid": "YOUR_FEE_ITEM_ID_HERE",
    "type": "YOUR_AC_TYPE_HERE",
    "level": "YOUR_AC_LEVEL_HERE",
    "campus": "YOUR_CAMPUS_HERE",
    "building": "YOUR_BUILDING_HERE",
    "floor": "YOUR_FLOOR_HERE",
    "room": "YOUR_ROOM_HERE"
}

# This value should not be used directly
# If you need to use AHU request header, please use ``get_ahu_header()`` function below to get up-to-date header info.
DORM_REQ_HEADER_DICT: dict | None = None


def get_ahu_header(force_load_from_file: bool = False) -> dict:
    """
    Get AHU provider header from ahu_header.json file and return it.

    :param force_load_from_file: If `true`, force to reload header from file.

    :return: headers info dict.
    """
    global DORM_REQ_HEADER_DICT

    # if the header has already been loaded to value, directly return
    if (DORM_REQ_HEADER_DICT is not None) and (not force_load_from_file):
        return DORM_REQ_HEADER_DICT

    # else, try to load the value from json file.
    header_data: dict | None = None
    with open('config/ahu_header.json', 'r', encoding='utf-8') as f:
        header_data = json.load(f)
    DORM_REQ_HEADER_DICT = header_data

    return DORM_REQ_HEADER_DICT


def update_ahu_header(
        url_str: str,
        clear_cache: bool = True,
) -> dict:
    """
    Update Authentication info in ahu_header.json.

    Parameters:

    - ``url_str``:

    The URL string that links to authorized AHU electrical info page. Since AHU Online System
    directly put the Authentication Token Info into the URL, we could extract the auth key from the URL and use it to
    update the auth info required in the header files.

    - ``clear_cache``: If `true`, clear the outdated ``DORM_REQ_HEADER_DICT`` header cache value in this file.

    Exceptions:

    - ``invalid_url_str`` Raised when there is no valid token info in passed URL string.
    """
    global DORM_REQ_HEADER_DICT

    # use regex to extract the auth token from URL
    match = re.search(r'token=(?P<jwt_token>[a-zA-Z0-9]*\.[a-zA-Z0-9]*\..*?)#', url_str)

    # if not found
    if match is None:
        raise exc.BaseError(
            name='invalid_url_str',
            message='Could not found valid token info in URL string',
            status=400)

    # if matched, get token string
    token_str: str = match.groupdict()['jwt_token']

    header = get_ahu_header(force_load_from_file=True)
    header['synjones-auth'] = 'bearer ' + token_str
    with open('config/ahu_header.json', 'w', encoding='utf-8') as f:
        json.dump(header, f)

    # clear cache if needed
    if clear_cache:
        DORM_REQ_HEADER_DICT = header

    return header
