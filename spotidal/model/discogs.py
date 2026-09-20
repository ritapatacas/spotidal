import sqlite3
from pathlib import Path

from .genre import ApiUnavailable, BudgetExhausted, DiscogsClient
from .helpers.type.file import Files
from .library import _normalize_match_text, _now


class _StdoutReport:
    def log(self, text):
        print(text)

    def warn(self, text):
        print(f"WARNING: {text}")


class DiscogsTaxonomyFiller:
    def __init__(self, database_path, report=None, max_calls=None):
        self.database_path = Path(database_path).expanduser().resolve()
        self._report = report or _StdoutReport()
        self._client = DiscogsClient(self._report, max_calls=max_calls)

    @property
    def client(self):
        return self._client

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def playlist_tracks(self, name):
        with self._connect() as connection:
            return connection.execute(
                "SELECT t.track_id, t.title, t.artist, t.album, t.isrc, t.year "
                "FROM playlist_tracks pt "
                "JOIN playlists p ON p.playlist_id = pt.playlist_id "
                "JOIN tracks t ON t.track_id = pt.track_id "
                "WHERE p.name = ? ORDER BY t.title COLLATE NOCASE",
                (name,),
            ).fetchall()

    def _bound_track_ids(self, connection):
        return {
            row[0]
            for row in connection.execute(
                "SELECT track_id FROM discogs_release WHERE is_selected = 1"
            )
        }

    @staticmethod
    def _search_queries(album, title):
        # Same variant order as GenreFiller._search_strict: the raw album is
        # the most specific, the cleaned one drops edition suffixes Discogs
        # does not carry ("Mosquito (Deluxe)"), and the title covers singles
        # and releases catalogued under the track name.
        from .genre import clean_query

        queries = []
        for candidate in (album, clean_query(album or ""), title):
            candidate = (candidate or "").strip()
            if not candidate:
                continue
            if all(
                _normalize_match_text(candidate) != _normalize_match_text(existing)
                for existing in queries
            ):
                queries.append(candidate)
        return queries

    def resolve(self, title, artist, album, isrc):
        # Album search first, ISRC second. The ISRC route goes through
        # MusicBrainz, which resolved to a Discogs release for only ~10% of
        # this library while costing a 1.1s call on every track -- roughly an
        # hour a night spent on the 90% that miss. The album search answers
        # ~89% on its own, so ISRC is the fallback, not the entry point.
        first_artist = (artist or "").split(",")[0].strip()
        if first_artist:
            for query in self._search_queries(album, title):
                # Each variant gets its own cache key, so a cached miss on the
                # raw "(Deluxe)" album does not hide a hit on the cleaned one.
                cache_key = f"search:{_normalize_match_text(query)}||" \
                            f"{_normalize_match_text(first_artist)}"
                cached = self._client.cached(cache_key)
                if cached is not None:
                    matches = cached.get("matches", [])
                else:
                    matches = self._client.search_release(query, first_artist) or []
                    self._client.store(cache_key, {"matches": matches[:5]})
                if matches:
                    return matches[0]["id"], "album_search", 0.8
        isrc = (isrc or "").strip()
        if isrc:
            release_id = self._client.isrc_to_discogs(isrc)
            if release_id:
                return release_id, "isrc", 0.95
        return None, None, None

    # ---- unattended harvest -------------------------------------------------

    MAX_UNMATCHED_ATTEMPTS = 3

    def selection_tracks(self):
        names = Files.SELECTION.load() or []
        if not names:
            return []
        with self._connect() as connection:
            placeholders = ",".join("?" for _ in names)
            return connection.execute(
                "SELECT DISTINCT t.track_id, t.title, t.artist, t.album, t.isrc "
                "FROM playlists p "
                "JOIN playlist_tracks pt ON pt.playlist_id = p.playlist_id "
                "JOIN tracks t ON t.track_id = pt.track_id "
                f"WHERE p.name IN ({placeholders}) "
                "ORDER BY t.artist COLLATE NOCASE, t.album COLLATE NOCASE",
                list(names),
            ).fetchall()

    def all_tracks(self):
        # Selection first, everything else after. A night run can be cut short
        # at any point, so the tracks the user actually cares about must be the
        # ones already done when it is.
        selected = self.selection_tracks()
        seen = {row[0] for row in selected}
        with self._connect() as connection:
            rest = connection.execute(
                "SELECT track_id, title, artist, album, isrc FROM tracks "
                "ORDER BY artist COLLATE NOCASE, album COLLATE NOCASE"
            ).fetchall()
        return selected + [row for row in rest if row[0] not in seen]

    HARVEST_SOURCE = "discogs"

    def _harvest_state(self, connection):
        return {
            row[0]: (row[1], row[2])
            for row in connection.execute(
                "SELECT track_id, attempts, outcome FROM harvest_log WHERE source = ?",
                (self.HARVEST_SOURCE,),
            )
        }

    def _record_attempt(self, track_id, outcome):
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO harvest_log(track_id, source, attempts, last_attempt_at, outcome) "
                "VALUES(?, ?, 1, ?, ?) "
                "ON CONFLICT(track_id, source) DO UPDATE SET "
                "attempts = attempts + 1, last_attempt_at = excluded.last_attempt_at, "
                "outcome = excluded.outcome",
                (track_id, self.HARVEST_SOURCE, _now(), outcome),
            )

    def _clear_attempt(self, connection, track_id):
        connection.execute(
            "DELETE FROM harvest_log WHERE track_id = ? AND source = ?",
            (track_id, self.HARVEST_SOURCE),
        )

    def harvest(self, rows, retry_unmatched=False):
        """Resolve tracks to Discogs releases and persist the taxonomy.

        Writes only the discogs_* tables -- never tracks.genre/style and never
        file tags. Safe to interrupt: progress lives in the database, so a
        relaunch skips whatever is already done.
        """
        stats = {"filled": 0, "skipped": 0, "unmatched": 0, "stopped": None}
        with self._connect() as connection:
            already = self._bound_track_ids(connection)
            state = self._harvest_state(connection)
        for track_id, title, artist, album, isrc in rows:
            if track_id in already:
                stats["skipped"] += 1
                continue
            attempts, outcome = state.get(track_id, (0, None))
            if (
                not retry_unmatched
                and outcome == "unmatched"
                and attempts >= self.MAX_UNMATCHED_ATTEMPTS
            ):
                stats["skipped"] += 1
                continue
            try:
                release_id, method, confidence = self.resolve(title, artist, album, isrc)
                detail = self._client.release_detail(release_id) if release_id else None
            except (ApiUnavailable, BudgetExhausted) as error:
                # The API is unwell or the budget ran out. Neither is this
                # track's fault, so leave its attempt count untouched and stop.
                stats["stopped"] = error
                break
            if not detail or not detail.get("genres"):
                stats["unmatched"] += 1
                self._record_attempt(track_id, "unmatched")
                continue
            with self._connect() as connection:
                self.store(
                    connection, track_id, int(release_id), detail, method, confidence
                )
                self._clear_attempt(connection, track_id)
            stats["filled"] += 1
            self._report.log(
                f"{title} - {artist} -> discogs:{release_id} "
                f"[{', '.join(detail['genres'])} / {', '.join(detail['styles'])}] ({method})"
            )
        self._client.flush()
        return stats

    def fill_playlist(self, name):
        done = skipped = unmatched = 0
        with self._connect() as connection:
            already = self._bound_track_ids(connection)
        for track_id, title, artist, album, isrc, _year in self.playlist_tracks(name):
            if track_id in already:
                skipped += 1
                continue
            release_id, method, confidence = self.resolve(title, artist, album, isrc)
            detail = self._client.release_detail(release_id) if release_id else None
            if not detail or not detail.get("genres"):
                unmatched += 1
                self._report.warn(f"no discogs genres found for '{title} - {artist}'")
                continue
            with self._connect() as connection:
                self.store(connection, track_id, int(release_id), detail, method, confidence)
            done += 1
            self._report.log(
                f"{title} - {artist} -> discogs:{release_id} "
                f"[{', '.join(detail['genres'])} / {', '.join(detail['styles'])}] ({method})"
            )
        self._client.flush()
        return {"filled": done, "skipped": skipped, "unmatched": unmatched}

    def store(
        self, connection, track_id, discogs_id, detail, method, confidence,
        selection_method="automatic", review_status="pending",
    ):
        year = detail.get("year")
        year = int(year) if str(year or "").isdigit() else None
        now = _now()
        connection.execute(
            "UPDATE discogs_release SET is_selected=0 WHERE track_id=? AND is_selected=1 "
            "AND discogs_id<>?",
            (track_id, discogs_id),
        )
        row = connection.execute(
            "SELECT discogs_release_id FROM discogs_release WHERE track_id=? AND discogs_id=?",
            (track_id, discogs_id),
        ).fetchone()
        if row:
            release_row_id = row[0]
            connection.execute(
                "UPDATE discogs_release SET is_selected=1, confidence=?, match_method=?, "
                "selection_method=?, review_status=?, "
                "master_id=?, title=?, year=?, label=?, catalog_number=?, updated_at=? "
                "WHERE discogs_release_id=?",
                (
                    confidence, method, selection_method, review_status,
                    detail.get("master_id"), detail.get("title"),
                    year, detail.get("label"), detail.get("catalog_number"), now,
                    release_row_id,
                ),
            )
        else:
            cursor = connection.execute(
                "INSERT INTO discogs_release(track_id, discogs_id, master_id, confidence, "
                "match_method, is_selected, review_status, selection_method, "
                "title, year, label, catalog_number, "
                "created_at, updated_at) VALUES(?,?,?,?,?,1,?,?,?,?,?,?,?,?)",
                (
                    track_id, discogs_id, detail.get("master_id"), confidence, method,
                    review_status, selection_method,
                    detail.get("title"), year, detail.get("label"),
                    detail.get("catalog_number"), now, now,
                ),
            )
            release_row_id = cursor.lastrowid
        genres = detail.get("genres") or []
        styles = detail.get("styles") or []
        for genre in genres:
            genre_id = self._ensure(connection, "genre", genre)
            if styles:
                for style in styles:
                    style_id = self._ensure(connection, "style", style)
                    connection.execute(
                        "INSERT OR IGNORE INTO discogs_release_genre_style VALUES(?,?,?)",
                        (release_row_id, genre_id, style_id),
                    )
            else:
                connection.execute(
                    "INSERT OR IGNORE INTO discogs_release_genre_style VALUES(?,?,NULL)",
                    (release_row_id, genre_id),
                )

    def _ensure(self, connection, table, name):
        name = (name or "").strip()
        row = connection.execute(
            f"SELECT {table}_id FROM {table} WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row[0]
        cursor = connection.execute(f"INSERT INTO {table}(name) VALUES(?)", (name,))
        return cursor.lastrowid

    @staticmethod
    def _tokens(text):
        return set(_normalize_match_text(text).split())

    def _weak_release(self, track_year, album, title, detail):
        album_tokens = self._tokens(album)
        title_tokens = self._tokens(title)
        rel_tokens = self._tokens(detail.get("title", ""))
        artists = {a.casefold() for a in detail.get("artists") or []}
        if "various artists" in artists or "[unknown]" in artists:
            return True
        if not rel_tokens & album_tokens and not rel_tokens & title_tokens:
            return True
        if detail.get("year") and track_year:
            try:
                if abs(int(detail["year"]) - int(track_year)) > 5:
                    return True
            except ValueError:
                pass
        return False

    def _full_detail(self, discogs_id):
        # Cache entries written before `artists` existed cannot feed the
        # weakness check; one forced re-fetch upgrades them permanently.
        detail = self._client.release_detail(discogs_id)
        if detail and "artists" not in detail:
            detail = self._client.release_detail(discogs_id, force=True)
        return detail

    def _selected_candidate(self, connection, track_id, artist):
        row = connection.execute(
            "SELECT discogs_release_id, discogs_id, master_id, title, year, label, "
            "catalog_number, confidence, match_method, review_status "
            "FROM discogs_release WHERE track_id=? AND is_selected=1",
            (track_id,),
        ).fetchone()
        if not row:
            return None
        genres, styles = set(), set()
        for name, style_id in connection.execute(
            "SELECT g.name, rgs.style_id FROM discogs_release_genre_style rgs "
            "JOIN genre g USING(genre_id) WHERE rgs.discogs_release_id=?",
            (row[0],),
        ):
            genres.add(name)
            if style_id is not None:
                styles.update(
                    s for (s,) in connection.execute(
                        "SELECT name FROM style WHERE style_id=?", (style_id,)
                    )
                )
        return {
            "discogs_id": row[1], "artist": artist, "title": row[3],
            "year": row[4], "label": row[5], "genres": sorted(genres),
            "styles": sorted(styles), "current": True,
        }

    def review_queue(self, name, force=False):
        queue = []
        with self._connect() as connection:
            for track in self.playlist_tracks(name):
                track_id, title, artist, album, _isrc, year = track
                if not force and connection.execute(
                    "SELECT 1 FROM track_genre_style WHERE track_id = ? LIMIT 1",
                    (track_id,),
                ).fetchone():
                    continue
                selected = connection.execute(
                    "SELECT discogs_id, confidence, review_status FROM discogs_release "
                    "WHERE track_id=? AND is_selected=1",
                    (track_id,),
                ).fetchone()
                if not selected:
                    queue.append((track, None))
                    continue
                discogs_id, confidence, status = selected
                if status == "approved" and not force:
                    continue
                if force:
                    queue.append((track, discogs_id))
                    continue
                if confidence is not None and confidence < 0.9:
                    queue.append((track, discogs_id))
                    continue
                detail = self._full_detail(discogs_id)
                if detail and self._weak_release(year, album, title, detail):
                    queue.append((track, discogs_id))
        self._client.flush()
        return queue

    def _candidate_label(self, candidate):
        genres = "/".join(candidate.get("genres") or [])
        styles = "/".join(candidate.get("styles") or [])
        taxonomy = " • ".join(part for part in (genres, styles) if part)
        year = candidate.get("year") or "?"
        label = f" [{candidate['label']}]" if candidate.get("label") else ""
        marker = "[atual] " if candidate.get("current") else ""
        return (
            f"{marker}{candidate.get('artist') or ''} - {candidate.get('title')} "
            f"({year}){label}" + (f" • {taxonomy}" if taxonomy else "")
        )

    def _gather_candidates(self, track, connection):
        track_id, title, artist, album, isrc, _year = track
        candidates = {}

        def add(candidate):
            discogs_id = candidate.get("discogs_id")
            if discogs_id is None:
                return
            candidates.setdefault(int(discogs_id), candidate)

        current = self._selected_candidate(connection, track_id, artist)
        if current:
            add(current)
        first_artist = (artist or "").split(",")[0].strip()
        if (isrc or "").strip():
            release_id = self._client.isrc_to_discogs(isrc.strip())
            if release_id:
                detail = self._client.release_detail(release_id) or {}
                add({
                    "discogs_id": release_id, "artist": artist,
                    "title": detail.get("title"), "year": detail.get("year"),
                    "label": detail.get("label"), "genres": detail.get("genres"),
                    "styles": detail.get("styles"),
                })
        def search(query, strict):
            if not query or not first_artist:
                return
            for match in self._client.search_release(query, first_artist, strict=strict):
                add({
                    "discogs_id": match["id"],
                    "artist": match["title"].split(" - ")[0],
                    "title": match["title"].split(" - ", 1)[-1],
                    "year": match.get("year"), "label": match.get("label"),
                    "genres": match.get("genres"), "styles": match.get("styles"),
                })

        album = (album or "").strip()
        title = (title or "").strip()
        search(album, True)
        search(title, True)
        if len(candidates) < 3:
            # same widening as the tags+db review: parenthetical suffixes like
            # "(Radio Edit)" break Discogs' release_title matching
            from .genre import clean_query
            queries = []
            for q in (clean_query(album), clean_query(title), album, title):
                q = (q or "").strip()
                if q and not any(q.casefold() == e.casefold() for e in queries):
                    queries.append(q)
            for query in queries:
                search(query, False)
            if not candidates:
                for match in (self._client.search_artist_releases(first_artist) if first_artist else []):
                    add({
                        "discogs_id": match["id"],
                        "artist": match["title"].split(" - ")[0],
                        "title": match["title"].split(" - ", 1)[-1],
                        "year": match.get("year"), "label": match.get("label"),
                        "genres": match.get("genres"), "styles": match.get("styles"),
                    })
        return list(candidates.values())

    def _manual_tags(self, connection, track_id):
        return [
            genre if style is None else f"{genre}/{style}"
            for genre, style in connection.execute(
                "SELECT g.name, s.name FROM track_genre_style tgs "
                "JOIN final_genre g USING(final_genre_id) "
                "LEFT JOIN style s USING(style_id) "
                "WHERE tgs.track_id = ? ORDER BY g.name, s.name",
                (track_id,),
            )
        ]

    def review_playlist(self, name, force=False):
        from InquirerPy import prompt as inquirer_prompt
        from InquirerPy.base.control import Choice

        queue = self.review_queue(name, force=force)
        self._report.log(
            f"review: {len(queue)} track(s) from '{name}' "
            f"({self._client.calls} api calls so far); ctrl-c volta atras"
        )
        approved = kept = skipped = manual_done = 0
        aborted = False
        for track, _selected_id in queue:
            if aborted:
                skipped += 1
                continue
            track_id, title, artist, album, _isrc, _year = track
            with self._connect() as connection:
                candidates = self._gather_candidates(track, connection)
                manual_tags = self._manual_tags(connection, track_id)
            seen = set()
            options = []
            for candidate in candidates:
                label = self._candidate_label(candidate)
                if label in seen:
                    continue
                seen.add(label)
                options.append(Choice(value=("release", candidate), name=label))
            if any(o.value[1].get("current") for o in options):
                options.append(Choice(value=("keep", None), name="manter a actual"))
            options.append(Choice(value=("search", None), name="nova pesquisa..."))
            options.append(Choice(value=("manual", None), name="classificação manual (1 genero + estilos opcionais)"))
            options.append(Choice(value=("skip", None), name="skip (reaparece na proxima revisao)"))
            message = f"discogs release for '{title} - {artist}'"
            if manual_tags:
                message += f" [manual: {', '.join(manual_tags)}]"
            while True:
                try:
                    answer = inquirer_prompt([{
                        "type": "list", "name": "choice",
                        "message": message + ":",
                        "choices": options,
                    }])
                except KeyboardInterrupt:
                    aborted = True
                    action, candidate = "skip", None
                    break
                action, candidate = answer.get("choice") or ("skip", None)
                if action == "manual":
                    result = self._prompt_manual(track_id, title, artist)
                    if result is None:
                        continue
                    if result:
                        manual_done += 1
                    else:
                        skipped += 1
                    action = "done"
                    break
                if action == "search":
                    try:
                        query = inquirer_prompt([{
                            "type": "input", "name": "query",
                            "message": "pesquisar por titulo do album/single (ctrl-c volta):",
                        }]).get("query", "").strip()
                    except KeyboardInterrupt:
                        continue
                    first_artist = (artist or "").split(",")[0].strip()
                    if not (query and first_artist):
                        continue
                    for match in self._client.search_release(query, first_artist):
                        candidates.append({
                            "discogs_id": match["id"],
                            "artist": match["title"].split(" - ")[0],
                            "title": match["title"].split(" - ", 1)[-1],
                            "year": match.get("year"), "label": match.get("label"),
                            "genres": match.get("genres"), "styles": match.get("styles"),
                        })
                    if not candidates:
                        self._report.warn(f"sem resultados para '{query}'")
                        continue
                    search_options = [
                        Choice(value=("release", c), name=self._candidate_label(c))
                        for c in candidates
                    ]
                    search_options.append(Choice(value=("back", None), name="voltar"))
                    try:
                        answer = inquirer_prompt([{
                            "type": "list", "name": "choice",
                            "message": f"escolher release para '{title} - {artist}':",
                            "choices": search_options,
                        }])
                    except KeyboardInterrupt:
                        continue
                    action, candidate = answer.get("choice") or ("back", None)
                    if action == "back":
                        continue
                    break
                break
            if action == "done":
                continue
            if aborted:
                skipped += 1
                continue
            if action == "skip":
                skipped += 1
                continue
            if action == "keep":
                with self._connect() as connection:
                    connection.execute(
                        "UPDATE discogs_release SET review_status='approved', updated_at=? "
                        "WHERE track_id=? AND is_selected=1",
                        (_now(), track_id),
                    )
                kept += 1
                self._report.log(f"kept: {title} - {artist}")
                continue
            if action != "release" or candidate is None:
                skipped += 1
                continue
            detail = self._full_detail(candidate["discogs_id"])
            if not detail or not detail.get("genres"):
                self._report.warn(f"release {candidate['discogs_id']} sem genres; skip")
                skipped += 1
                continue
            with self._connect() as connection:
                connection.execute(
                    "UPDATE discogs_release SET is_selected=0, review_status='approved' "
                    "WHERE track_id=? AND is_selected=1",
                    (track_id,),
                )
                self.store(
                    connection, track_id, int(candidate["discogs_id"]), detail,
                    "manual", 1.0, selection_method="manual", review_status="approved",
                )
            approved += 1
            self._report.log(
                f"reviewed: {title} - {artist} -> discogs:{candidate['discogs_id']} "
                f"[{', '.join(detail['genres'])} / {', '.join(detail['styles'])}]"
            )
            self._client.flush()
        self._client.flush()
        return {
            "reviewed": approved, "kept": kept,
            "manual": manual_done, "skipped": skipped,
        }

    def _prompt_manual(self, track_id, title, artist):
        from InquirerPy import prompt as inquirer_prompt

        with self._connect() as connection:
            genres = [
                row[0] for row in connection.execute(
                    "SELECT name FROM final_genre ORDER BY name"
                )
            ]
            styles = [
                row[0] for row in connection.execute("SELECT name FROM style ORDER BY name")
            ]
        choices = genres + ["+ criar genero novo", "cancelar"]
        genre = None
        while genre is None:
            try:
                answer = inquirer_prompt([{
                    "type": "list", "name": "genre",
                    "message": f"genero final para '{title} - {artist}' (ctrl-c volta):",
                    "choices": choices,
                }]).get("genre")
            except KeyboardInterrupt:
                return None
            if not answer or answer == "cancelar":
                return None
            if answer == "+ criar genero novo":
                try:
                    name = inquirer_prompt([{
                        "type": "input", "name": "new_genre",
                        "message": "nome do novo genero final (ctrl-c volta):",
                    }]).get("new_genre", "").strip()
                except KeyboardInterrupt:
                    continue
                if not name:
                    continue
                with self._connect() as connection:
                    genre_id = self._ensure(connection, "final_genre", name)
                self._report.log(f"novo genero final: {name} (id {genre_id})")
                genre = name
            else:
                genre = answer
        picked = []
        if styles:
            try:
                picked = inquirer_prompt([{
                    "type": "checkbox", "name": "styles",
                    "message": "estilos finais (opcional; espaco marca, enter confirma):",
                    "choices": styles,
                }]).get("styles") or []
            except KeyboardInterrupt:
                return None
        with self._connect() as connection:
            genre_id = self._ensure(connection, "final_genre", genre)
            connection.execute(
                "DELETE FROM track_genre_style WHERE track_id = ?", (track_id,)
            )
            if picked:
                for style in picked:
                    style_id = self._ensure(connection, "style", style)
                    connection.execute(
                        "INSERT OR IGNORE INTO track_genre_style VALUES(?,?,?)",
                        (track_id, genre_id, style_id),
                    )
            else:
                connection.execute(
                    "INSERT OR IGNORE INTO track_genre_style VALUES(?,?,NULL)",
                    (track_id, genre_id),
                )
            connection.execute(
                "UPDATE discogs_release SET review_status='approved', updated_at=? "
                "WHERE track_id=? AND is_selected=1",
                (_now(), track_id),
            )
        self._report.log(
            f"manual: {title} - {artist} -> "
            + (", ".join(f"{genre}/{s}" for s in picked) if picked else genre)
        )
        return True
