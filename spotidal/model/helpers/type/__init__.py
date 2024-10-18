from .config import SpotifyConfig, TidalConfig, PlaylistConfig, SyncConfig
from .spotify import SpotifyTrack
from .playlist_ref import PlaylistReference

TidalID = str
SpotifyID = str

from tidalapi import Session, Track

TidalSession = Session
TidalTrack = Track

__all__ = [
    "SpotifyConfig",
    "TidalConfig",
    "PlaylistConfig",
    "SyncConfig",
    "TidalID",
    "SpotifyID",
    "TidalSession",
    "TidalTrack",
    "SpotifyTrack",
    "PlaylistReference",
]
