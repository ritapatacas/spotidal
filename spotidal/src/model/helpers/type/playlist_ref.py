import re
from enum import Enum
from ..utils import get_parsed_playlists


class PlaylistReference(Enum):
    SP_ID = 1
    TD_ID = 2
    NAME = 3

    @classmethod
    def resolver(cls, element):
        e = element
        if isinstance(element, list):
            e = e[0]
        if cls.is_sp_id(e):
            return cls.SP_ID
        if cls.is_td_id(e):
            return cls.TD_ID
        else:
            return cls.NAME

    @staticmethod
    def is_sp_id(id_str):
        id_regex = re.compile(r'^[a-zA-Z0-9]{22}$')
        return bool(id_regex.match(id_str))

    @staticmethod
    def is_td_id(id_str):
        id_regex = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
        return bool(id_regex.match(id_str))

    @classmethod
    def get_info(cls, reference):
        parsed_playlists = get_parsed_playlists()
        ref_type = cls.resolver(reference)

        for p in parsed_playlists:
            if ref_type == cls.SP_ID and p['sp_id'] == reference:
                return p
            elif ref_type == cls.TD_ID and p['td_id'] == reference:
                return p
            elif ref_type == cls.NAME and (p['name'] == reference):
                return p

        return None
