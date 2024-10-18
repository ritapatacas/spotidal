from ..model import Model
from ..model.helpers.type import PlaylistReference as playlist


class PlaylistController:
    def __init__(self, model: Model):
        self._model = model

    # kinda playlist ref resolver
    def get_name(self, ref):
        print(playlist.get_info(ref))
        return playlist.get_info(ref)["name"]

    def names(self):
        return self._model.get_playlist_names()


    def load(self):
        return self._model.get_saved_selection()

    def save(self, selected_playlists):
        self._model.save_selection(selected_playlists)

    def get_selection(self):
        return self._model.current_selection
    
    def add_to_selection(self, e):
        self._model.current_selection.add(e)
        
    def not_selected(self):
        playlists = set(self.names())
        remaining_playlists = playlists - self._model.current_selection 
        return list(remaining_playlists)

        
if __name__ == "__main__":
    controller = PlaylistController()
