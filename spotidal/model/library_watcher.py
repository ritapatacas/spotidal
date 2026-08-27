from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


SUPPORTED = {".flac", ".mp3"}


class LibraryEventHandler(FileSystemEventHandler):
    def __init__(self, library, location_id, location_name, location_type, root_path):
        self.library = library
        self.location_id = location_id
        self.location_name = location_name
        self.location_type = location_type
        self.root_path = Path(root_path).expanduser().resolve()

    def _audio(self, path):
        path = Path(path)
        return (
            path.suffix.lower() in SUPPORTED
            and not path.name.startswith("._")
            and path.resolve().is_relative_to(self.root_path)
        )

    def _import(self, path):
        if self._audio(path) and Path(path).is_file():
            try:
                self.library.import_file(
                    path,
                    location_name=self.location_name,
                    location_type=self.location_type,
                )
            except (OSError, ValueError, KeyError):
                pass

    def _mark_missing(self, path):
        path = Path(path)
        if not self.root_path.is_dir() or not self._audio(path):
            return
        try:
            relative = path.resolve().relative_to(
                self.root_path
            ).as_posix()
        except ValueError:
            return
        self.library.mark_missing(self.location_id, relative)

    def on_created(self, event):
        if event.is_directory and Path(event.src_path).resolve() == self.root_path:
            self.library.reconcile_location(self.location_id)
        elif not event.is_directory:
            self._import(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._import(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._mark_missing(event.src_path)

    def on_moved(self, event):
        if event.is_directory and Path(event.dest_path).resolve() == self.root_path:
            self.library.reconcile_location(self.location_id)
        elif not event.is_directory:
            self._mark_missing(event.src_path)
            self._import(event.dest_path)


class LibraryWatcher:
    def __init__(self, library):
        self.library = library
        self.observer = Observer()

    def refresh(self):
        self.library.reconcile_all()

    def start(self):
        for location_id, name, root_path, location_type in self.library.locations():
            root = Path(root_path).expanduser()
            watch_root = root
            while not watch_root.is_dir() and watch_root != watch_root.parent:
                watch_root = watch_root.parent
            self.observer.schedule(
                LibraryEventHandler(
                    self.library, location_id, name, location_type, root
                ),
                str(watch_root),
                recursive=True,
            )
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.observer.join(timeout=5)
