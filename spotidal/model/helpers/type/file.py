import os
import json
import yaml
from enum import Enum
from tidalapi import playlist


class Path(Enum):
    USR = '~/.config/spotidal/'
    TD_DL_NG = '~/.config/tidal_dl_ng/'


class Ext(Enum):
    JSON = '.json'
    YML = '.yml'
    TXT = '.txt'


class Files(Enum):
    DEFAULT_SETTINGS = Path.USR, 'default_settings', Ext.JSON
    SETTINGS = Path.TD_DL_NG, 'settings', Ext.JSON
    PLAYLISTS = Path.USR, 'playlists', Ext.JSON
    PARSED_PLAYLISTS = Path.USR, 'parsed_playlists', Ext.YML
    SELECTION = Path.USR, 'selection', Ext.JSON
    NOT_FOUND = Path.USR, 'not_found', Ext.YML
    CREDENTIALS = Path.USR, "credentials", Ext.YML

    def save(self, data, playlist_name=None):
        file_path = self.resolver(self, playlist_name)
        _, _, file_ext = self.value
        
        # create file if it doesn't exist
        if not os.path.exists(file_path):
            with open(file_path, 'w', encoding="utf-8") as f:
                pass

        try:
            if file_ext == Ext.TXT:
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(data)
            elif file_ext == Ext.JSON:
                with open(file_path, 'w', encoding="utf-8") as f:
                    json.dump(data, f, indent=4)

            elif file_ext == Ext.YML:
                with open(file_path, 'w', encoding="utf-8") as f:
                    yaml.dump(data, f)
            else:
                raise ValueError(f"unsupported file extension: {file_ext}")
        except Exception as e:
            print(f"error occurred while writing to file: {str(e)}")

    def load(self):
        file_path = self.resolver(self)
        _, _, file_ext = self.value

        try:
            with open(file_path, 'r') as file:
                if file_ext == Ext.JSON:
                    return json.load(file)
                elif file_ext == Ext.YML:
                    return yaml.safe_load(file)
                elif file_ext == Ext.TXT:
                    return file.read()
                else:
                    raise ValueError(f"unsupported file ext {file_ext}")
        except FileNotFoundError:
            print(f"file not found: {file_path}. Creating a new file.")
            self.save({})
            return {}

    @classmethod
    def resolver(cls, file_enum, playlist_name=None):
        path, file_name, ext = file_enum.value
        if file_enum == cls.NOT_FOUND and playlist_name:
            file_name = f"{file_name}/{playlist_name}"
        return os.path.expanduser(os.path.join(path.value, file_name + ext.value))