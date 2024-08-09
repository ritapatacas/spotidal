import tidalapi
import auth_td as _auth_td


#if there is no tidal_playlist:
def create_new_playlist(playlist):
        td = _auth_td.get_session()
        print(f" > No playlist found on Tidal with name: '{playlist['name']}', creating new playlist")
        return td.user.create_playlist(playlist['name'], "")
