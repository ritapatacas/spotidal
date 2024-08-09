import os
import json

def get_file_path(file_name):
    project_root = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..'))
    #os.makedirs(project_root, exist_ok=True)
    return os.path.join(project_root, file_name)


def save_to_json(data, file_name):
    file = get_file_path(file_name)

    with open(file, 'w') as file:
        json.dump(data, file, indent=4)

    print(" > Saved to ", file_name)

def load_playlists_from_json(file_name):
    file = get_file_path(file_name)
    with open(file, 'r') as file:
        data = json.load(file)
    return data

def header():
    print("\n\n  ###########################                  ###########################\n  ########################        SPOTIDAL        ########################\n  ###########################                  ###########################\n\n\n")

