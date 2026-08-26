"""Extract the Spotify playlist folder hierarchy from the desktop app's local cache.

The Spotify Web API does not expose folders. The desktop client stores the
"rootlist" (ordered playlists + folder markers) as a protobuf value inside a
LevelDB database at PersistentCache/Users/<user>-user/primary.ldb. We read the
sstable (.ldb) and write-ahead log (.log) files directly, pick the newest
rootlist value, and parse the ordered URIs:

    spotify:playlist:<id>
    spotify:start-group:<hex>:<url-encoded name>
    spotify:end-group:<hex>

This is an undocumented format and may break with Spotify updates; callers
should treat a None/empty result as "folders unavailable".
"""

import glob
import os
import re
import struct
import sys
from urllib.parse import unquote_plus

import cramjam

_LDB_MAGIC = bytes.fromhex("57fb808b247547db")
_URI_RE = re.compile(
    rb"spotify:(?:playlist:[A-Za-z0-9]{22}|start-group:[0-9a-f]+:.+|end-group:[0-9a-f]+)"
)


def _candidate_dirs():
    home = os.path.expanduser("~")
    roots = [
        os.path.join(home, "Library", "Application Support", "Spotify"),  # macOS
        os.path.join(home, ".config", "spotify"),  # Linux
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Spotify"),  # Windows
    ]
    if sys.platform.startswith("linux"):
        roots.append(os.path.join(home, ".var", "app", "com.spotify.Client", "config", "spotify"))
    dirs = []
    for root in roots:
        dirs += glob.glob(os.path.join(root, "PersistentCache", "Users", "*-user", "primary.ldb"))
        dirs += glob.glob(os.path.join(root, "Users", "*-user", "primary.ldb"))
    return dirs


def _varint(buf, i):
    r = s = 0
    while True:
        b = buf[i]
        i += 1
        r |= (b & 0x7F) << s
        s += 7
        if not b & 0x80:
            return r, i


def _block_entries(blk):
    n_restarts = struct.unpack("<I", blk[-4:])[0]
    end = len(blk) - 4 - 4 * n_restarts
    i = 0
    prev = b""
    while i < end:
        shared, i = _varint(blk, i)
        non_shared, i = _varint(blk, i)
        vlen, i = _varint(blk, i)
        key = prev[:shared] + blk[i : i + non_shared]
        i += non_shared
        value = blk[i : i + vlen]
        i += vlen
        prev = key
        yield key, value


def _ldb_entries(path):
    """Yield (user_key, seq, type, value) from a LevelDB sstable file."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 48 or data[-8:] != _LDB_MAGIC:
        return
    footer = data[-48:]
    _, i = _varint(footer, 0)
    _, i = _varint(footer, i)
    ioff, i = _varint(footer, i)
    isz, i = _varint(footer, i)

    def get_block(off, sz):
        raw = data[off : off + sz]
        if data[off + sz] == 1:
            return bytes(cramjam.snappy.decompress_raw(raw))
        return raw

    for _, handle in _block_entries(get_block(ioff, isz)):
        boff, j = _varint(handle, 0)
        bsz, j = _varint(handle, j)
        for ikey, value in _block_entries(get_block(boff, bsz)):
            trailer = struct.unpack("<Q", ikey[-8:])[0]
            yield ikey[:-8], trailer >> 8, trailer & 0xFF, value


def _log_entries(path):
    """Yield (user_key, seq, type, value) from a LevelDB write-ahead log."""
    with open(path, "rb") as f:
        data = f.read()
    # reassemble records from 32KB blocks
    records = []
    partial = b""
    pos = 0
    while pos + 7 <= len(data):
        block_off = pos % 32768
        if 32768 - block_off < 7:
            pos += 32768 - block_off
            continue
        length, rtype = struct.unpack("<HB", data[pos + 4 : pos + 7])
        payload = data[pos + 7 : pos + 7 + length]
        pos += 7 + length
        if rtype == 1:  # full
            records.append(payload)
        elif rtype == 2:  # first
            partial = payload
        elif rtype == 3:  # middle
            partial += payload
        elif rtype == 4:  # last
            records.append(partial + payload)
            partial = b""
        else:
            break
    for batch in records:
        if len(batch) < 12:
            continue
        seq = struct.unpack("<Q", batch[:8])[0]
        count = struct.unpack("<I", batch[8:12])[0]
        i = 12
        try:
            for n in range(count):
                typ = batch[i]
                i += 1
                klen, i = _varint(batch, i)
                key = batch[i : i + klen]
                i += klen
                value = b""
                if typ == 1:
                    vlen, i = _varint(batch, i)
                    value = batch[i : i + vlen]
                    i += vlen
                yield key, seq + n, typ, value
        except IndexError:
            continue


def _newest_rootlist(ldb_dir):
    # Several key families end in ":rootlist#"; only the "!pl#slc#" one holds
    # the actual list, and it may appear in multiple files. Keep the newest
    # (highest sequence number) value that actually contains playlist URIs.
    best = (-1, None)
    files = glob.glob(os.path.join(ldb_dir, "*.ldb")) + glob.glob(os.path.join(ldb_dir, "*.log"))
    for path in files:
        reader = _ldb_entries if path.endswith(".ldb") else _log_entries
        try:
            for key, seq, typ, value in reader(path):
                if (
                    key.endswith(b":rootlist#")
                    and typ == 1
                    and b"spotify:playlist" in value
                    and seq > best[0]
                ):
                    best = (seq, value)
        except Exception:
            continue
    return best[1]


def _ordered_uris(rootlist):
    """Walk the rootlist protobuf and return contained URIs in document order."""
    uris = []

    def walk(buf):
        i = 0
        while i < len(buf):
            try:
                tag, i = _varint(buf, i)
            except IndexError:
                return
            wt = tag & 7
            if wt == 2:
                ln, i = _varint(buf, i)
                v = buf[i : i + ln]
                i += ln
                if _URI_RE.fullmatch(v):
                    uris.append(v.decode())
                elif b"spotify:" in v:
                    walk(v)
            elif wt == 0:
                _, i = _varint(buf, i)
            elif wt == 5:
                i += 4
            elif wt == 1:
                i += 8
            else:
                return

    walk(rootlist)
    return uris


def get_playlist_folders():
    """Return {playlist_id: [folder, subfolder, ...]} or None if unavailable."""
    for ldb_dir in _candidate_dirs():
        rootlist = _newest_rootlist(ldb_dir)
        if not rootlist:
            continue
        uris = _ordered_uris(rootlist)
        if not uris:
            continue
        mapping = {}
        stack = []
        for uri in uris:
            parts = uri.split(":", 3)
            kind = parts[1]
            if kind == "start-group":
                stack.append(unquote_plus(parts[3]))
            elif kind == "end-group":
                if stack:
                    stack.pop()
            elif kind == "playlist" and stack:
                mapping[parts[2]] = list(stack)
        return mapping
    return None
