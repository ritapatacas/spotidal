import sys
import asyncio
import utils
import td_fetch as _td_fetch
import sp_fetch as _sp_fetch


async def fetch_playlists(sessions):
    playlists = {
        'sp': _sp_fetch.get_playlists_names_ids(sessions['sp']),
        'td': await _td_fetch.get_playlists_names_ids(sessions['td'])
    }
    return playlists


async def save_playlists_to_json(playlists):
    print("\n\n> Saving playlists to json")
    utils.save_to_json(playlists['sp'], 'user_data/spotify_playlists.json')
    utils.save_to_json(playlists['td'], 'user_data/tidal_playlists.json')

    # matches = await find_matching_playlists(sp_playlists, td_playlists)

def load_playlists_from_json():
    playlists = {
        'sp': utils.load_playlists_from_json('user_data/spotify_playlists.json'),
        'td': utils.load_playlists_from_json('user_data/tidal_playlists.json')
    }
    return playlists

async def fetch_and_save_playlists(sessions):
    playlists = await fetch_playlists(sessions)
    await save_playlists_to_json(playlists)

async def find_matching_playlists(playlists):
    matches = []

    sp_playlists = playlists['sp']
    td_playlists = playlists['td']

    print(
        f"\n\n> Looking for matches for {len(sp_playlists)} spotify playlists\n")

    for sp_playlist in sp_playlists:
        for td_playlist in td_playlists:
            if sp_playlist['name'] == td_playlist['name']:
                matches.append({sp_playlist['name']: {'sp': sp_playlist['id'], 'td': td_playlist['id'], 'sync': sp_playlist['sync']}})
                print(f"    Match! {sp_playlist['name']}")
                break
    print(f"\n> Found: {len(matches)}")
    utils.save_to_json(matches, 'user_data/matching_playlists.json')
    return matches
