# Spotidal

Transfers your Spotify playlists to TIDAL.
Bridging the gap in the music streaming wars, one playlist at a time.

## TL;DR

```bash
pip install poetry
poetry install
poetry run spotidal
```

First run will ask for your Spotify credentials — see [credentials](#credentials).

## What

A simple Python app that syncs your playlists and automates the downloading of TIDAL tracks

- **Search** and **select** Spotify playlists, or
- **Load** a previously saved **playlist selection** to
- **Sync** playlists or
- **Download** tracks directly from TIDAL
- Includes a **log for 404 not found tracks**

## Usage

```bash
poetry run spotidal            # interactive menu
poetry run spotidal sync-all   # sync every Spotify playlist to TIDAL, no menu
poetry run spotidal-web        # web interface
```

- `sync-all` fetches all your Spotify playlists (paginated, no 50-playlist limit) and syncs each one to TIDAL, printing progress as `[i/total] syncing '<name>'`.

## Credentials

### Spotify

You need your `username`, a `client ID` and a `client secret`:

1. Find your `username` in your account settings or profile URL.
2. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and choose `Create App`.
3. Fill in a `Name` and `Description`, set both `Website` and `Redirect URIs` to `http://127.0.0.1:8888/callback`, and check the `Web API` box.
4. Copy the `Client ID` and `Client Secret` from the app settings.

### TIDAL

Obtained automatically — just open the link shown in your browser and accept the connection.

Downloads use `tidekeeper`, a maintained fork of Tidal-Media-Downloader, and it is installed automatically when
needed. To install it manually, run `python -m pip install -U tidekeeper`.

### Credentials file

Stored in `~/.config/spotidal/credentials.yml`:

```yaml
spotify:
  client_id: <your_client_id>
  client_secret: <your_client_secret>
  username: <your_username>
  redirect_uri: http://127.0.0.1:8888/callback
  scope: playlist-read-private, user-library-read
  requests_timeout: 2

tidal:
  access_token: <your_access_token>
  refresh_token: <your_refresh_token>
  session_id: <your_session_id>
  token_type: Bearer
```

## To-do

- [ ] Simplify setup and ensure all critical files are ready
- [ ] Improve search functionality for missing tracks
- [ ] Optimize the sync process for TIDAL tracks
- [ ] Make TIDAL tracks persist across syncs
- [ ] Fully integrate TIDAL playlist track downloads

## Credits

This project began as a fork of [spotify_to_tidal](https://github.com/spotify2tidal), combined with the [python-tidal](https://github.com/tamland/python-tidal) algorithm.
It was built for personal use and learning purposes. There is an automation feature that uses [tidal-media-downloader](https://github.com/yaronzz/Tidal-Media-Downloader).
Thanks to everyone involved!

_Does this project solve a major problem?_
_Will this automation end anyone's suffering?_
_Probably not._
_But did I enjoy it building it...?_
