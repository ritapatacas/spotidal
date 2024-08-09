import os
import sys
import json
import yaml
import webbrowser
import tidalapi
from plyer import notification


project_root = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..'))
os.makedirs(project_root, exist_ok=True)
session_file_path = os.path.join(project_root, 'tidal_session.yml')


def open_tidal_session() -> tidalapi.Session:
    session = tidalapi.Session()
    login, future = session.login_oauth()
    print('Login with the webbrowser: ' + login.verification_uri_complete)
    url = login.verification_uri_complete
    if not url.startswith('https://'):
        url = 'https://' + url
    webbrowser.open(url)
    future.result()
    try:
        with open(session_file_path, 'w') as f:
            yaml.dump({
                'tidal': {
                    'session_id': session.session_id,
                    'token_type': session.token_type,
                    'access_token': session.access_token,
                    'refresh_token': session.refresh_token
                }
            }, f)
        print("\nTidal Session saved\n")
    except OSError as e:
        print("Error saving Tidal Session: \n" + str(e))
    return session


def get_session() -> tidalapi.Session:
    try:
        with open(session_file_path, 'r') as session_file:
            previous_session = yaml.safe_load(session_file)
            print("Previous Tidal Session loaded\n")
    except OSError:
        previous_session = None
    session = tidalapi.Session()
    if previous_session:
        try:
            if session.load_oauth_session(
                token_type=previous_session['tidal']['token_type'],
                access_token=previous_session['tidal']['access_token'],
                refresh_token=previous_session['tidal']['refresh_token']
            ):
                return session
        except Exception as e:
            print("Error loading previous Tidal Session: \n" + str(e))
    else:
        print("No previous Tidal Session found, opening new session")
        open_tidal_session()



""" def get_tidal_client():
    return tidalapi.Session()

session = get_tidal_client()
print(session)

login, future = session.login_oauth()

notification.notify("Open the URL to log in", login.verification_uri_complete)
 """
