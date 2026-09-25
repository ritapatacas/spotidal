import sys
import time
import warnings
from spotidal.model.model import Model
from spotidal.controller.playlist_controller import PlaylistController
from spotidal.controller.controller_main import ControllerMain

import spotidal.view.view as view
from spotidal.view.sound import play_task_done
from spotidal.view.text import Text as t
from spotidal.model.helpers.td_downloader import (
    TidalSessionStaleError,
    pop_conversion_messages,
)
from spotidal.model.helpers.sync.search import pop_not_found_tracks
from spotidal.view.setup import get_credentials

from spotidal.view.prompt import (
    MainMenu,
    SelectionModeMenu,
    SettingsMenu,
    UtilsMenu,
)


warnings.filterwarnings(
    "ignore", category=DeprecationWarning, module=r"spotipy\.client"
)
warnings.filterwarnings(
    "ignore", category=DeprecationWarning, module=r"tidalapi\.session"
)


class Controller:
    def __init__(self):
        self.model = Model()
        self.init_sessions()
        self.app = ControllerMain(self.model)
        print(t.busy(f"download dir: {self.app.get_download_dir()}"))
        for warning in self.app.get_startup_warnings():
            print(t.warning(warning))
        self.playlists = PlaylistController(self.model)




    def init_sessions(self):
        sp = self.model.open_sp_session()
        if not sp:
            self.model.setup_credentials(get_credentials())
            sp = self.model.open_sp_session()
        try:
            td = self.model.open_td_session()
        except Exception as e:
            sys.exit(t.error(f"unable to authenticate with TIDAL: {e}"))
        if not td:
            sys.exit(t.error("unable to authenticate with TIDAL; please try again"))
        self.model.sessions = {"sp": sp, "td": td}

        log = self.model.get_session_log()
        for account in log.splitlines():
            print(t.busy(account))

    def _select_menu(self, playlists):
        preselected = self.model.current_selection or set(self.playlists.load())
        return view.select_menu(playlists, preselected)

    def _prompt_url_and(self, on_url):
        url = view.url_menu()
        if url:
            try:
                on_url(url)
            except ValueError as error:
                print(t.error(str(error)))

    def _run_task(self, func, *args, **kwargs):
        started = time.monotonic()
        result = func(*args, **kwargs)
        not_found = pop_not_found_tracks()
        if not_found:
            print(t.error(
                f"{len(not_found)} track(s) not found: {', '.join(not_found)}"
            ))
        self.app.resolve_original_album_choices()
        delay = self.app.get_notify_sound_delay()
        if delay and (time.monotonic() - started) >= delay * 60:
            play_task_done()
        return result

    def run(self):
        while True:
            try:
                for message in pop_conversion_messages():
                    print(message)
                menu = view.main_menu()
                if menu == MainMenu.QUIT[0]:
                    self.app.stop_library_monitoring()
                    print(t.log("quitting!"))
                    sys.exit()
                elif menu == MainMenu.SETTINGS[0]:
                    action = view.settings_menu()
                    if action == SettingsMenu.DOWNLOAD_SETTINGS:
                        self._download_settings()
                    elif action == SettingsMenu.DATABASE_SETTINGS:
                        self._database_settings()
                    elif action == SettingsMenu.NOTIFICATIONS_SETTINGS:
                        self._notifications_settings()
                    elif action == SettingsMenu.HELP:
                        print(t.log(
                            "spotidal — sync and download playlists from Spotify via TIDAL.\n"
                            "  download: pick playlists and download them\n"
                            "  sync: pick playlists and keep them in sync\n"
                            "  convert: convert downloaded FLAC files to MP3\n"
                            "  explore library: browse/filter your local library and get mixing suggestions (opens a browser tab)\n"
                            "  utils: playlist selection, tmp cleanup, session refresh, database tools, rekordbox export\n"
                            "  settings: downloads and database configuration"
                        ))

                elif menu == MainMenu.UTILS[0]:
                    self._utils_menu()

                elif menu == MainMenu.SYNC[0] or menu == MainMenu.DOWNLOAD[0]:
                    if self.model.current_selection:
                        print(t.display_selection(self.model.current_selection))
                    action = view.selection_mode_menu(
                        True, include_missing_tracks=(menu == MainMenu.DOWNLOAD[0])
                    )

                    if action == SelectionModeMenu.DOWNLOAD_MISSING:
                        self._run_task(self.app.download_current_missing_tracks)
                        continue

                    if action == SelectionModeMenu.SEARCH[0]:
                        playlists = (
                            self.playlists.names()
                            if menu == MainMenu.DOWNLOAD[0]
                            else self.playlists.not_selected()
                        )
                        selected = view.search_menu(playlists)
                        if not selected:
                            continue
                        self.model.current_selection.add(selected)

                    elif action == SelectionModeMenu.SELECT[0]:
                        result = self._select_menu(self.playlists.names())
                        if result is None:
                            continue
                        self.model.current_selection = set(result)

                    elif action == SelectionModeMenu.LOAD:
                        selection = set(self.playlists.load())
                        if menu == MainMenu.DOWNLOAD[0]:
                            filtered = self.app.filter_playlists_with_missing(selection)
                            skipped = len(selection) - len(filtered)
                            if skipped:
                                print(t.log(
                                    f"skipped {skipped} playlist(s) already fully downloaded"
                                ))
                            selection = filtered
                        self.model.current_selection = selection

                    elif action == SelectionModeMenu.URL:
                        self._prompt_url_and(lambda url: self._run_task(
                            self.app.download_url if menu == MainMenu.DOWNLOAD[0]
                            else self.app.sync_url,
                            url,
                        ))
                        continue

                    elif action == SelectionModeMenu.BACK[0]:
                        continue

                    if not action:
                        continue
                    if menu == MainMenu.SYNC[0]:
                        self._run_task(self.app.sync, list(self.model.current_selection))
                    elif menu == MainMenu.DOWNLOAD[0]:
                        self._run_task(self.app.download, list(self.model.current_selection))
                        self.model.current_selection = set()

                elif menu == MainMenu.CONVERT[0]:
                    self._run_task(self.app.flac_to_mp3)

                elif menu == MainMenu.SEARCH[0]:
                    self._run_task(self.app.run_search_ui)

            except KeyboardInterrupt:
                self.app.stop_library_monitoring()
                print(t.log("quitting!"))
                sys.exit()
            except TidalSessionStaleError:
                print(t.error(
                    "TIDAL session is stale; refreshing access token before continuing"
                ))
                if self.app.refresh_td_session():
                    print(t.log("TIDAL access token refreshed"))
                else:
                    print(t.warning("unable to refresh TIDAL access token"))
            except Exception as error:
                print(t.error(f"error: {error}"))

    def _download_settings(self):
        while True:
            action = view.download_settings_menu()
            if self._is_back(action):
                return
            if action == "download directory":
                self.app.change_download_dir()
            elif action == "audio quality":
                self.app.change_audio_quality()
            elif action == "automatic mp3 conversion":
                self.app.toggle_mp3_conversion()
            elif action == "tidekeeper additional settings":
                self._tidekeeper_settings()

    def _default_selection(self):
        while True:
            action = view.default_selection_menu()
            if self._is_back(action):
                return
            if action == "view selection":
                selection = self.playlists.load()
                if not selection:
                    print("> no default playlists selected")
                else:
                    stats = self.app.get_selection_stats(selection)
                    print(t.display_selection_table(stats))
            elif action == "refresh selection stats":
                selection = self.playlists.load()
                if not selection:
                    print("> no default playlists selected")
                else:
                    stats = self._run_task(self.app.get_selection_stats, selection, force_refresh=True)
                    print(t.display_selection_table(stats))
            elif action == "change selection":
                selection = view.select_menu(
                    self.playlists.names(), self.playlists.load()
                )
                if selection:
                    self.playlists.save(selection)
                    print(t.log("default playlist selection saved"))

    def _watch_playlist_files(self):
        selection = set()
        while True:
            if selection:
                print(t.display_selection(selection))
            action = view.selection_mode_menu(True)
            if action in (None, SelectionModeMenu.BACK[0]):
                return
            if action == SelectionModeMenu.SEARCH[0]:
                selected = view.search_menu(self.playlists.not_selected())
                if selected:
                    selection.add(selected)
            elif action == SelectionModeMenu.SELECT[0]:
                result = view.select_menu(self.playlists.names(), selection)
                if result is not None:
                    selection = set(result)
            elif action == SelectionModeMenu.LOAD:
                selection |= set(self.playlists.load())
            elif action == SelectionModeMenu.URL:
                self._prompt_url_and(
                    lambda url: selection.add(
                        self.app.resolve_playlist_name_from_url(url)
                    )
                )
            if not selection:
                continue
            if view.confirm_selection_menu():
                break
        stats = self._run_task(self.app.get_selection_stats, selection, force_refresh=True)
        print(t.display_selection_table(stats))

    def _utils_menu(self):
        self._run_submenu(UtilsMenu.UTILS_Q, UtilsMenu.UTILS_OPT, {
            UtilsMenu.PLAYLISTS: self._utils_playlists,
            UtilsMenu.DOWNLOAD: self._utils_download,
            UtilsMenu.LOCAL_FILES: self._utils_local_files,
            UtilsMenu.DATABASE: self._utils_database,
            UtilsMenu.GENRES: self._utils_genres,
        })

    def _run_submenu(self, title, options, handlers):
        submenu = view.Submenu(title, options)
        while True:
            action = submenu.display()
            if action is None:
                return
            handler = handlers.get(action)
            if handler:
                handler()

    @staticmethod
    def _is_back(action):
        return action in (None, "back")

    def _utils_playlists(self):
        self._run_submenu(UtilsMenu.PLAYLISTS, UtilsMenu.PLAYLISTS_OPT, {
            UtilsMenu.MANAGE_SELECTED_PLAYLIST: self._default_selection,
            UtilsMenu.DOCTOR_PLAYLISTS: lambda: self._run_task(self.app.doctor_playlists),
            UtilsMenu.WATCH_PLAYLIST_FILES: self._watch_playlist_files,
            UtilsMenu.EXPORT_REKORDBOX: lambda: self._run_task(self.app.export_rekordbox),
        })

    def _utils_download(self):
        self._run_submenu(UtilsMenu.DOWNLOAD, UtilsMenu.DOWNLOAD_OPT, {
            UtilsMenu.DOCTOR_DOWNLOAD: lambda: self._run_task(self.app.doctor_download),
            UtilsMenu.DOCTOR_MISSING_TRACKS: lambda: self._run_task(self.app.doctor_missing_tracks),
            UtilsMenu.DOWNLOAD_CURRENT_MISSING: lambda: self._run_task(self.app.download_current_missing_tracks),
            UtilsMenu.TIDEKEEPER_DOCTOR: self.app.tidekeeper_doctor,
            UtilsMenu.CLEAN_TMP: lambda: self._run_task(self.app.clean_tmp),
            UtilsMenu.REFRESH_SESSION: self._refresh_tidal_session,
        })

    def _refresh_tidal_session(self):
        if self.app.refresh_td_session():
            print(t.log("TIDAL access token refreshed"))
        else:
            print(t.warning("unable to refresh TIDAL access token"))

    def _utils_local_files(self):
        self._run_submenu(UtilsMenu.LOCAL_FILES, UtilsMenu.LOCAL_FILES_OPT, {
            UtilsMenu.DOCTOR_MP3_QUALITY: lambda: self._run_task(self.app.doctor_mp3_quality),
            UtilsMenu.CONVERT_TO_FLAC: lambda: self._run_task(self.app.normalize_to_flac),
            UtilsMenu.RUN_WATCHER: lambda: self._run_task(self.app.reconcile_library),
            UtilsMenu.WATCH_PLAYLIST_FILES: self._watch_playlist_files,
            UtilsMenu.EXPORT_REKORDBOX: lambda: self._run_task(self.app.export_rekordbox),
            UtilsMenu.AUDIT_CONSISTENCY: self._audit_consistency,
        })

    def _audit_consistency(self):
        names = self._select_menu(self.app.playlist_names())
        if names:
            self._run_task(self.app.audit_playlist_consistency, names)

    def _utils_database(self):
        self._run_submenu(UtilsMenu.DATABASE, UtilsMenu.DATABASE_OPT, {
            UtilsMenu.DOCTOR_PLAYLISTS: lambda: self._run_task(self.app.doctor_playlists),
            UtilsMenu.RUN_WATCHER: lambda: self._run_task(self.app.reconcile_library),
            UtilsMenu.WATCH_PLAYLIST_FILES: self._watch_playlist_files,
            UtilsMenu.FIX_MISSING_DATA: lambda: self._run_task(self.app.fill_missing_database_data),
            UtilsMenu.FILL_GENRES: lambda: self._run_task(self.app.fill_genres),
            UtilsMenu.IMPORT_REKORDBOX_BPM_KEY: lambda: self._run_task(self.app.import_rekordbox_metadata),
        })

    def _utils_genres(self):
        self._run_submenu(UtilsMenu.GENRES, UtilsMenu.GENRES_OPT, {
            UtilsMenu.VIEW_GENRES: self._view_genres,
            UtilsMenu.VIEW_GENRE_STYLES: self._view_genre_styles,
            UtilsMenu.ADD_GENRE_STYLE: self._add_genre_style,
            UtilsMenu.FILL_GENRES: self._fill_genres_scoped,
            UtilsMenu.FILL_GENRES_RYM: self._harvest_rym_scoped,
        })

    def _view_genres(self):
        rows = self.app.final_genres()
        if not rows:
            print(t.log("no genres defined"))
            return
        for name, count in rows:
            print(t.log(f"{name} ({count} track(s))"))

    def _view_genre_styles(self):
        self._run_submenu(UtilsMenu.VIEW_GENRE_STYLES, UtilsMenu.VIEW_STYLES_OPT, {
            UtilsMenu.ALL_GENRES: self._print_genre_styles,
            UtilsMenu.SELECT_GENRE: self._print_genre_styles_for_selected_genre,
        })

    def _print_genre_styles_for_selected_genre(self):
        genres = [row[0] for row in self.app.final_genres()]
        if not genres:
            print(t.log("no genres defined"))
            return
        genre = view.ListMenu("select genre", genres).display()
        if genre:
            self._print_genre_styles(genre)

    def _print_genre_styles(self, genre_name=None):
        rows = self.app.final_genre_styles(genre_name)
        if not rows:
            print(t.log("no styles classified yet"))
            return
        for genre, style, count in rows:
            print(t.log(f"{genre} / {style} ({count} track(s))"))

    def _add_genre_style(self):
        genre = view.InputMenu("new genre (empty to skip)").display()
        style = view.InputMenu("new style (empty to skip)").display()
        if not genre and not style:
            print(t.log("nothing added"))
            return
        if genre:
            genre_id, created = self.app.add_final_genre(genre)
            if created:
                print(t.log(f"genre '{genre.strip()}' added"))
        if style:
            style_id, created = self.app.add_style(style)
            if created:
                print(t.log(f"style '{style.strip()}' added"))

    def _fill_genres_scoped(self):
        self._run_submenu(UtilsMenu.FILL_GENRES, UtilsMenu.FILL_GENRES_OPT, {
            UtilsMenu.FILL_SELECTED: self._fill_genres_for_default_selection,
            UtilsMenu.FILL_SELECT_PLAYLISTS: self._fill_genres_for_chosen_playlists,
        })

    def _fill_genres_for_default_selection(self):
        names = self.playlists.load()
        if not names:
            print(t.warning("no default selection; use 'select playlists'"))
            return
        self._fill_genres_for_playlists(names)

    def _fill_genres_for_chosen_playlists(self):
        names = self._select_menu(self.app.playlist_names())
        if names:
            self._fill_genres_for_playlists(names)

    def _fill_genres_for_playlists(self, names):
        track_ids = self.app.track_ids_for_playlists(names)
        if not track_ids:
            print(t.warning(
                f"no local tracks found for: {', '.join(sorted(names))}"
            ))
            return
        print(t.log(
            f"filling genres for {len(track_ids)} track(s) in "
            f"{', '.join(sorted(names))}"
        ))
        self._run_task(self.app.fill_genres, track_ids)

    def _harvest_rym_scoped(self):
        self._run_submenu(UtilsMenu.FILL_GENRES_RYM, UtilsMenu.FILL_RYM_OPT, {
            UtilsMenu.FILL_SELECTED: lambda: self._harvest_rym_scope("selection"),
            UtilsMenu.FILL_ALL: lambda: self._harvest_rym_scope("all"),
            UtilsMenu.FILL_SELECT_PLAYLISTS: self._harvest_rym_scope_chosen_playlists,
        })

    def _harvest_rym_scope_chosen_playlists(self):
        names = self._select_menu(self.app.playlist_names())
        if names:
            self._harvest_rym_scope(names)

    def _harvest_rym_scope(self, scope):
        from spotidal.model.settings import Settings
        from spotidal.model.rym import RymTaxonomyFiller

        settings = Settings()
        if not settings.get_database_enabled():
            print(t.error("database is disabled"))
            return
        values = settings.get_settings()
        filler = RymTaxonomyFiller(
            settings.get_database_path(),
            max_pages=values.get("rymMaxPages", 80),
            min_delay=values.get("rymMinDelay", 10),
            max_delay=values.get("rymMaxDelay", 25),
        )
        if isinstance(scope, list):
            rows = []
            for name in scope:
                rows.extend(_harvest_scope_rows(filler, name))
            label = ", ".join(sorted(scope))
        else:
            rows = _harvest_scope_rows(filler, scope)
            label = scope
        if not rows:
            print(t.warning(f"no tracks found for scope '{label}'"))
            return
        print(t.busy(f"rym harvest: {len(rows)} track(s) in scope '{label}'"))
        stats, error = _run_rym_harvest_or_report(
            lambda: self._run_task(_rym_harvest, filler, rows)
        )
        if error:
            return
        _log_rym_stats(stats)

    def _notifications_settings(self):
        while True:
            action = view.notifications_settings_menu()
            if self._is_back(action):
                return
            if action == "notification sound delay (minutes)":
                value = view.notification_delay_menu(self.app.get_notify_sound_delay())
                if value is None:
                    continue
                try:
                    minutes = max(0.0, float(value))
                except ValueError:
                    print(t.error("invalid number of minutes"))
                    continue
                self.app.set_notify_sound_delay(minutes)
                print(t.log(
                    "notification sound disabled"
                    if minutes == 0
                    else f"notification sound threshold set to {minutes:g} minute(s)"
                ))

    def _database_settings(self):
        while True:
            action = view.database_settings_menu()
            if self._is_back(action):
                return
            self.app.change_database_option(action)

    def _tidekeeper_settings(self):
        while True:
            action = view.tidekeeper_settings_menu()
            if self._is_back(action):
                return
            print(t.log(f"Tidekeeper setting '{action}' will be implemented later"))

    def run_doctor(self, scope):
        methods = {
            "download": self.app.doctor_download,
            "playlists": self.app.doctor_playlists,
            "missing": self.app.doctor_missing_tracks,
            "mp3": self.app.doctor_mp3_quality,
        }
        if scope in ("all", "doctor"):
            return self.app.doctor_all()
        if scope not in methods:
            print(t.error(
                f"unknown doctor scope '{scope}'; "
                f"use one of: {', '.join(methods)}, all"
            ))
            return False
        return methods[scope]()


def _parse_harvest_args(args):
    source, scope, retry, max_calls, max_pages = "discogs", "selection", False, None, None
    positional = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--retry-unmatched":
            retry = True
        elif arg == "--max-calls":
            index += 1
            max_calls = int(args[index]) if index < len(args) else None
        elif arg.startswith("--max-calls="):
            max_calls = int(arg.split("=", 1)[1])
        elif arg == "--max-pages":
            index += 1
            max_pages = int(args[index]) if index < len(args) else None
        elif arg.startswith("--max-pages="):
            max_pages = int(arg.split("=", 1)[1])
        else:
            positional.append(arg)
        index += 1
    if positional and positional[0] in ("discogs", "rym"):
        source = positional.pop(0)
    if positional:
        scope = positional[0]
    return source, scope, retry, max_calls, max_pages


HARVEST_USAGE = (
    "usage: spotidal harvest [selection|all|<playlist>] [--retry-unmatched] "
    "[--max-calls N]\n"
    "       spotidal harvest rym [selection|all|<playlist>] [--retry-unmatched] "
    "[--max-pages N]"
)


def _harvest_scope_rows(filler, scope):
    """Resolve a harvest scope string to (track_id, title, artist, album, year) rows."""
    if scope == "selection":
        return filler.selection_tracks()
    if scope == "all":
        return filler.all_tracks()
    return [row[:5] for row in filler.playlist_tracks(scope)]


def _rym_harvest(filler, rows, retry=False):
    """Run the semi-assisted RYM harvest, always closing the browser at the end.

    The real Chrome window opens lazily on the first request. SiteBlocked and
    BudgetExhausted are handled inside ``filler.harvest`` and surface through
    ``stats['stopped']`` instead of being raised.
    """
    print(t.warning(
        "rym: opening a real Chrome window now; keep it visible and be ready "
        "to resolve an 'I'm not a robot' challenge when one appears"
    ))
    try:
        return filler.harvest(rows, retry_unmatched=retry)
    finally:
        filler.client.close()


def _run_rym_harvest_or_report(run):
    """Run a zero-arg RYM harvest callable, reporting the shared failure message."""
    try:
        return run(), None
    except Exception as error:
        print(t.error(f"rym harvest failed: {error}"))
        print(t.log(
            "install the browser once with: poetry run playwright install chrome"
        ))
        return None, error


def _log_harvest_stats(stats, label="harvest"):
    print(t.log(
        f"{label} done: {stats['filled']} filled, "
        f"{stats['skipped']} skipped, {stats['unmatched']} unmatched"
    ))
    stopped = stats["stopped"]
    if stopped is not None:
        print(t.warning(f"stopped early: {stopped}"))
    return stopped


def _log_rym_stats(stats):
    return _log_harvest_stats(stats, label="rym harvest")


def run_harvest_cli(args):
    """Harvest taxonomy from an external service into the library database.

    ``spotidal harvest rym ...`` runs the semi-assisted RYM harvest through a
    real, visible Chrome window and needs a human nearby; ``spotidal harvest ...``
    (no source) keeps meaning the fully unattended Discogs harvest, so the
    existing cron/launchd jobs keep working unchanged.

    Deliberately does not build the Controller: this job needs only the local
    SQLite database. Opening Spotify/TIDAL sessions would add a slow startup
    and, worse, `init_sessions` exits the process when TIDAL auth has gone
    stale -- which would kill a 3am run for a reason that has nothing to do
    with the harvest.
    """
    from spotidal.model.settings import Settings

    try:
        source, scope, retry, max_calls, max_pages = _parse_harvest_args(args)
    except (ValueError, IndexError):
        print(t.error(HARVEST_USAGE))
        return 1

    settings = Settings()
    if not settings.get_database_enabled():
        print(t.error("database is disabled"))
        return 1
    if source == "rym":
        return _run_rym_harvest_cli(settings, scope, retry, max_pages)
    return _run_discogs_harvest_cli(settings, scope, retry, max_calls)


def _run_discogs_harvest_cli(settings, scope, retry, max_calls):
    from spotidal.model.discogs import DiscogsTaxonomyFiller
    from spotidal.model.genre import BudgetExhausted

    filler = DiscogsTaxonomyFiller(settings.get_database_path(), max_calls=max_calls)
    rows = _harvest_scope_rows(filler, scope)
    if not rows:
        print(t.warning(f"no tracks found for scope '{scope}'"))
        return 0
    print(t.busy(
        f"harvest: {len(rows)} track(s) in scope '{scope}'"
        f" ({'authenticated' if filler.client.authenticated else 'anonymous'})"
    ))
    stats = filler.harvest(rows, retry_unmatched=retry)
    stopped = _log_harvest_stats(stats)
    if stopped is None:
        return 0
    return 3 if isinstance(stopped, BudgetExhausted) else 2


def _run_rym_harvest_cli(settings, scope, retry, max_pages):
    from spotidal.model.rym import RymTaxonomyFiller
    from spotidal.model.genre import BudgetExhausted

    values = settings.get_settings()
    filler = RymTaxonomyFiller(
        settings.get_database_path(),
        max_pages=(
            max_pages if max_pages is not None else values.get("rymMaxPages", 80)
        ),
        min_delay=values.get("rymMinDelay", 10),
        max_delay=values.get("rymMaxDelay", 25),
    )
    rows = _harvest_scope_rows(filler, scope)
    if not rows:
        print(t.warning(f"no tracks found for scope '{scope}'"))
        return 0
    print(t.busy(f"rym harvest: {len(rows)} track(s) in scope '{scope}'"))
    stats, error = _run_rym_harvest_or_report(lambda: _rym_harvest(filler, rows, retry))
    if error:
        return 1
    stopped = _log_rym_stats(stats)
    if stopped is None:
        return 0
    return 3 if isinstance(stopped, BudgetExhausted) else 2


def main():
    print(f"\n{t.red('Spotidal')}\n")
    args = sys.argv[1:]
    if args and args[0] == "harvest":
        try:
            sys.exit(run_harvest_cli(args[1:]))
        except KeyboardInterrupt:
            print(t.log("interrupted; progress is saved, relaunch to resume"))
            sys.exit(130)
    controller = Controller()
    if args and args[0] == "doctor":
        scope = args[1] if len(args) > 1 else "all"
        try:
            success = controller.run_doctor(scope)
        except KeyboardInterrupt:
            controller.app.stop_library_monitoring()
            print(t.log("quitting!"))
            sys.exit(130)
        controller.app.stop_library_monitoring()
        sys.exit(0 if success else 1)
    controller.run()


if __name__ == "__main__":
    main()
