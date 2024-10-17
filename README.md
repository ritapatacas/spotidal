# Spotidal
An app threesome that offers you love.  
Enhances your quality of life by transferring your Spotify playlists to TIDAL.  
Bridging the gap in the music streaming wars, one playlist at a time.


A simple Python app that syncs your playlists and automates the downloading of TIDAL tracks.

- [Spotidal](#spotidal)
  - [Features](#features)
  - [Install](#install)
  - [Setup](#setup)
        - [Spotify Credentials](#spotify-credentials)
        - [Tidal Credentials](#tidal-credentials)
      - [Credentials file](#credentials-file)
  - [To-do](#to-do)
  - [Credits](#credits)






## Features

- **Search** and **select** Spotify playlists, or  
- **Load** a previously saved **playlist selection** to  
- **Sync** playlists or  
- **Download** tracks directly from TIDAL  
- Includes a **log for 404 not found tracks**


## Install

Navigate to project root directory and install all dependencies:

```bash
pip install -e .   
```

To start up the app run the command-script:
```bash
spotidal
```

First time you use it it will ask you about your spotify credentials.
You can also do it manually, either way check the next section to find where to get your credentials.


## Setup
##### Spotify Credentials

To use the Spotify API, you'll need your Spotify credentials.
Besides your `username`, you will need to get a `client ID` and a `client secret` by registering an app in [Spotify for Developers](https://developer.spotify.com/). Follow these steps to obtain them:

1. Find your Spotify `username` either in your account settings or in your Spotify profile URL.
2. Go to the [Spotify for Developers](https://developer.spotify.com/) website and log in.
3. Navigate to `Dashboard` > `Create App`.
4. Choose a `Name` for your app.
5. Provide a `Description` (you can write anything).
6. Set the `Website` to `http://localhost:8888/callback`.
7. Define the `Redirect URIs` as `http://localhost:8888`.
8. Check the `Web API` box.

Once the app is created, copy the `Client ID` and `Client Secret` from your app settings.

##### Tidal Credentials
We will get your Tidal Credentials automatically. You just need to open a link in your browser and accept the connection to this app.

#### Credentials file
Spotidal will use these credentials, which should be stored in a `credentials.yaml` file located in the `~/.config/spotidal` directory.
Credentials file structure should look like this:

```yaml
spotify:
  client_id: <your_client_id>
  client_secret: <your_client_secret>
  username: <your_username>
  redirect_uri: http://localhost:8888
  scope: "user-library-read playlist-read-private user-follow-read playlist-modify-private playlist-modify-public"
  max_concurrency: 10
  rate_limit: 10

tidal:
  access_token: <your_access_token>
  refresh_token: <your_refresh_token>
  session_id: <your_session_id>
  token_type: Bearer
```

---

## To-do  
- [ ] Simplify setup and ensure all critical files are ready  
- [ ] Improve search functionality for missing tracks  
- [ ] Optimize the sync process for TIDAL tracks  
- [ ] Make TIDAL tracks persist across syncs  
- [ ] Fully integrate TIDAL playlist track downloads


---

## Credits

This project began as a fork of [spotify_to_tidal](https://github.com/spotify2tidal), combined with the [python-tidal](https://github.com/tamland/python-tidal) algorithm.  
It was built for personal use and learning purposes. There is an automation feature that uses [tidal-media-downloader](https://github.com/yaronzz/Tidal-Media-Downloader).  
Thanks to everyone involved!


_Does this project solve a major problem?_
_Will this automation end anyone's suffering?_
_Probably not._
_But did I enjoy it building it...?_ 