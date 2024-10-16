# Setup Spotify Credentials

To use the Spotify API, you'll need your Spotify `username`, `client ID`, and `client secret`. Follow these steps to obtain them:

### Find Your Credentials

##### Username
Find your Spotify `username` either in your account settings or in your Spotify profile URL.

##### Client Credentials
1. Go to the [Spotify for Developers](https://developer.spotify.com/) website and log in.
2. Navigate to `Dashboard` > `Create App`.
3. Choose a `Name` for your app.
4. Provide a `Description` (you can write anything).
5. Set the `Website` to `http://localhost:8888/callback`.
6. Define the `Redirect URIs` as `http://localhost:8888`.
7. Check the `Web API` box.

Once the app is created, copy the `Client ID` and `Client Secret` from your app settings.

### Usage
Spotidal will use these credentials, which should be stored in a `credentials.yaml` file located in the `~/.config/spotidal` directory.

The credentials file structure should look like this:

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