from flask import Flask, request, jsonify
from spotidal.model.model import Model
from spotidal.controller.playlist_controller import PlaylistController
from spotidal.controller.controller_main import ControllerMain
from spotidal.view.text import Text as t
from spotidal.model.sync import Sync

app = Flask(__name__)

class Controller:
    def __init__(self):
        self.model = Model()
        self.init_sessions()
        self.app = ControllerMain(self.model)
        self.playlists = PlaylistController(self.model)
        self.sync = Sync(self.model.sessions)

    def init_sessions(self):
        sp = self.model.open_sp_session()
        td = self.model.open_td_session()
        if not sp:
            self.app.reset_sp_session()
        self.model.sessions = {"sp": sp, "td": td}
        log = self.model.get_session_log()
        print(t.log_grey(log))

controller = Controller()

@app.route('/sync_playlist', methods=['POST'])
def sync_playlist():
    playlist_name = request.json.get('playlist_name')
    controller.sync.by_sp_id(playlist_name)
    return jsonify({"status": f"playlist '{playlist_name}' synced"})

@app.route('/sync_all_playlists', methods=['POST'])
def sync_all_playlists():
    controller.sync.saved_selection()
    return jsonify({"status": "all playlists synced"})

@app.route('/sync_saved_selection', methods=['POST'])
def sync_saved_selection():
    controller.sync.saved_selection()
    return jsonify({"status": "saved selection synced"})

if __name__ == '__main__':
    app.run(debug=True)