# Importing playlists into rekordbox

How to get downloaded Spotidal playlists into rekordbox as real, analyzed
tracks, without duplicating anything already in your collection.

## Steps

1. **Run the export.**
   `export to rekordbox` (main menu) - this writes, under `<downloadPath>/rekordbox/`:
   - `rekordbox.xml` — is an XML tree with the picked playlists, nested by
     folder, carrying title/artist/album/genre/year metadata.
   - `playlists/*.m3u8` — one plain playlist file per playlist (fallback only,
     see [m3u8 vs XML](#m3u8-vs-xml) below).

2. **Import from the XML tree.**
   In rekordbox: `Preferences > Advanced > Database > rekordbox xml`, browse
   to `<downloadPath>/rekordbox/rekordbox.xml`, save.

   Drag the playlist (or subfolder) you want into your real collection /
   playlist panel. Rekordbox analyzes and adds those tracks to your
   **Collection** and creates a matching playlist there — a real import, not
   a live link to the XML file.

3. **Re-running later.**
   Re-run the export, reload the rekordbox xml source if rekordbox doesn't
   auto-refresh it, and only drag the playlists that actually changed.

## Avoiding duplicate tracks

Rekordbox matches XML tracks against your Collection by file path
(`Location`), so a track already in your Collection won't be re-added as a
new Collection entry.

**Playlist membership doesn't dedupe the same way.** Dragging the same
playlist node in twice can add the same track to that playlist twice — it's
"add these tracks to this playlist," not "sync this playlist."

Rule of thumb: **drag each playlist in at most once.** After that, manage it
by hand in rekordbox, or delete the old playlist first before dragging in a
refreshed one.

## m3u8 vs XML

Use the XML import. The `.m3u8` files are a fallback for skimming playlist
contents outside rekordbox — importing them directly has no metadata and
duplicates tracks on every re-import.

## Troubleshooting

- **BPM/key not showing after import** — that's the other direction: use
  `utils > doctors > database doctors > import bpm/key from rekordbox (update db)`
  to pull BPM/key rekordbox already analyzed back *into* Spotidal's DB.
