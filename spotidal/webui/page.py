_RETRO_CSS = """
  :root {
    --desktop: #000080;
    --face: #c0c0c0;
    --titlebar: #000080;
    --titlebar-fg: #ffffff;
    --text: #000000;
    --muted: #4a4a4a;
    --select-bg: #000080;
    --select-fg: #ffffff;
  }
  * { box-sizing: border-box; -webkit-font-smoothing: none; font-smooth: never; }
  html, body {
    margin: 0; width: 100%; height: 100%; background: var(--desktop); overflow: hidden;
    font-family: "MS Sans Serif", Geneva, Tahoma, sans-serif; font-size: 11px; color: var(--text);
  }

  #window {
    width: 480px; max-width: 92vw; min-width: 320px; min-height: 260px;
    background: var(--face); border: 2px outset var(--face); position: fixed; z-index: 10;
    display: flex; flex-direction: column; overflow: hidden;
  }

  .menubar {
    display: flex; flex: none; background: var(--face); gap: 2px; padding: 2px;
    border-bottom: 1px solid #808080;
  }
  .menubar .menu-item { padding: 6px 12px; font-size: 13px; }

  .resize-handle {
    position: absolute; right: 0; bottom: 0; width: 14px; height: 14px;
    border-top: 1px solid #fff; border-left: 1px solid #fff; cursor: nwse-resize; z-index: 2;
  }

  .titlebar {
    background: var(--titlebar); color: var(--titlebar-fg);
    padding: 8px 8px 8px 10px; display: flex; align-items: center;
    justify-content: space-between; font-weight: bold; font-size: 16px;
    cursor: move; user-select: none;
    font-family: "Home Video", "MS Sans Serif", Geneva, Tahoma, sans-serif;
  }
  .titlebar .name { display: flex; align-items: center; gap: 8px; overflow: hidden; }
  .titlebar .name .label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .icon16 {
    width: 18px; height: 18px; display: inline-grid; grid-template-columns: 1fr 1fr;
    grid-template-rows: 1fr 1fr; border: 1px solid #000; flex: none;
  }
  .icon16 span:nth-child(1) { background: #ff0000; }
  .icon16 span:nth-child(2) { background: #00a000; }
  .icon16 span:nth-child(3) { background: #0000ff; }
  .icon16 span:nth-child(4) { background: #ffff00; }
  .titlebar .btns { display: flex; gap: 4px; flex: none; }
  .titlebar button {
    width: 22px; height: 20px; font-size: 13px; line-height: 1; font-weight: bold;
    background: var(--face); color: #000; cursor: pointer; padding: 0;
    border: 1px outset var(--face); font-family: inherit;
  }
  .titlebar button:active { border-style: inset; }

  #body { padding: 8px; flex: 1; overflow-y: auto; min-height: 0; }

  .field {
    width: 100%; padding: 3px 4px; font-family: inherit; font-size: 12px;
    background: #fff; color: var(--text); border: 2px inset var(--face);
  }
  .field:focus { outline: none; }

  #q { font-size: 13px; padding: 5px 6px; }

  fieldset#filters-panel {
    margin: 8px 0 0; padding: 14px 12px 12px; border: 2px groove var(--face);
    display: none;
  }
  fieldset#filters-panel.open { display: block; }
  fieldset#filters-panel legend { padding: 0 4px; color: var(--text); }

  .filter-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .filter-grid .span2 { grid-column: 1 / -1; }
  .filter-grid label { display: block; margin-bottom: 2px; color: var(--text); }
  .bpm-slider { position: relative; height: 24px; margin-top: 6px; }
  .bpm-slider input[type=range] {
    position: absolute; left: 0; right: 0; top: 8px; width: 100%; margin: 0;
    background: none; -webkit-appearance: none; appearance: none; pointer-events: none;
  }
  .bpm-slider input[type=range]::-webkit-slider-runnable-track {
    height: 2px; background: #808080;
  }
  .bpm-slider input[type=range]::-webkit-slider-thumb {
    -webkit-appearance: none; pointer-events: auto; width: 14px; height: 14px;
    background: var(--face); border: 2px outset var(--face); cursor: pointer; margin-top: -6px;
  }
  .bpm-slider input[type=range]::-moz-range-track { height: 2px; background: #808080; }
  .bpm-slider input[type=range]::-moz-range-thumb {
    pointer-events: auto; width: 12px; height: 12px;
    background: var(--face); border: 2px outset var(--face); cursor: pointer;
  }
  .bpm-slider-labels { text-align: center; color: var(--muted); font-size: 12px; margin-top: 2px; }

  select.field { border-radius: 0; }


  #results { margin-top: 8px; background: #fff; max-height: 55vh; overflow-y: auto; border: 2px inset var(--face); }
  #results.hidden { display: none; }

  table.results-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  table.results-table th {
    position: sticky; top: 0; background: var(--face); text-align: left;
    padding: 4px 6px; border-bottom: 1px solid #808080; cursor: pointer;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  table.results-table th:hover { background: #d4d4d4; }
  table.results-table th .arrow { font-size: 9px; }
  table.results-table th.col-title { width: 23%; }
  table.results-table th.col-artist { width: 19%; }
  table.results-table th.col-album { width: 17%; }
  table.results-table th.col-genre { width: 18%; }
  table.results-table th.col-key { width: 12%; }
  table.results-table th.col-bpm { width: 11%; }
  table.results-table td {
    padding: 5px 6px; border-bottom: 1px dotted #b0b0b0;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  table.results-table tr.track-row { cursor: pointer; }
  table.results-table tr.track-row:hover { background: #dcdcf5; }
  table.results-table tr.track-row.active { background: var(--select-bg); color: var(--select-fg); }
  .artist-link { text-decoration: underline; cursor: pointer; }
  .artist-link:hover { color: #000080; }
  tr.active .artist-link:hover { color: #d8d8ff; }

  #dialog-body { padding: 14px; flex: 1; overflow-y: auto; min-height: 0; }
  #sug-list { background: #fff; max-height: 280px; overflow-y: auto; border: 2px inset var(--face); }
  .sug-row { padding: 5px 7px; border-bottom: 1px dotted #b0b0b0; cursor: pointer; }
  .sug-row:hover { background: #dcdcf5; }
  .sug-row .sug-title { font-weight: bold; }
  .sug-row .sug-sub { color: var(--muted); margin-top: 1px; }
  .empty { padding: 24px; text-align: center; color: var(--muted); }

  #dialog {
    width: 340px; max-width: 92vw; min-width: 300px; min-height: 220px;
    background: var(--face); border: 2px outset var(--face);
    position: fixed; top: 70px; left: calc(50% - 170px); z-index: 30; display: none;
    flex-direction: column; overflow: hidden;
  }
  #dialog.open { display: flex; }

  ::-webkit-scrollbar { width: 15px; height: 15px; }
  ::-webkit-scrollbar-track { background: var(--face); }
  ::-webkit-scrollbar-thumb { background: var(--face); border: 1px outset var(--face); }
  ::-webkit-scrollbar-corner { background: var(--face); }

  #taskbar {
    display: flex; align-items: center; gap: 8px; padding: 5px 8px;
    border-top: 2px outset var(--face); background: var(--face);
    position: fixed; left: 0; right: 0; bottom: 0; width: 100%; height: 46px; z-index: 20;
  }
  #start-btn, #search-btn {
    padding: 6px 14px 6px 8px; font-weight: bold; font-family: inherit; font-size: 13px;
    border: 2px outset var(--face); background: var(--face); cursor: pointer;
    display: flex; align-items: center; gap: 6px; height: 34px;
  }
  #start-btn.open, #start-btn:active, #search-btn:active {
    border-style: inset;
  }

  #start-menu {
    position: fixed; left: 6px; bottom: 46px; width: 260px; font-size: 14px;
    background: var(--face); border: 2px outset var(--face); display: none; z-index: 21; padding: 8px;
  }
  #start-menu.open { display: block; }
  .menu-item {
    position: relative; padding: 8px 10px; cursor: pointer;
    display: flex; align-items: center; gap: 9px; color: var(--text);
  }
  .menu-item:hover { background: var(--select-bg); color: var(--select-fg); }
  .menu-item .swatch {
    width: 16px; height: 16px; flex: none; border: 1px solid #000;
  }
  .menu-item .label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .menu-item .caret { flex: none; font-size: 11px; }
  .menu-sep { border-top: 1px solid #808080; border-bottom: 1px solid #fff; margin: 3px 2px; }
  .submenu {
    /* fixed (not absolute-inside-the-scrollable-parent): an ancestor .submenu
       with overflow-y:auto also clips the X axis, which silently clipped any
       nested flyout extending past its box. JS sets left/top on open. */
    position: fixed; width: 320px; font-size: 14px; color: var(--text);
    background: var(--face); border: 2px outset var(--face); display: none; z-index: 6; padding: 8px;
    max-height: 70vh; overflow-y: auto;
  }
  .submenu.open { display: block; }
  .menu-item.leaf .swatch { background: #ffd400; }

  .camelot-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px; margin-top: 4px; }
  .camelot-key {
    padding: 6px 2px; text-align: center; font-weight: bold; cursor: pointer;
    border: 2px outset #ccc; color: #000;
  }
  .camelot-key:active { border-style: inset; }
  .camelot-key.dim { opacity: 0.35; }
  .camelot-key.selected { outline: 2px solid #000; outline-offset: -4px; }
  .camelot-key.related { outline: 2px solid #fff; outline-offset: -4px; box-shadow: 0 0 0 1px #000; }
  .camelot-label { margin-top: 8px; color: var(--muted); font-size: 10px; text-transform: uppercase; }
"""


PAGE_HTML = (
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>spotidal</title>
<style>
"""
    + _RETRO_CSS
    + """
</style>
</head>
<body>

<div id="window">
  <div class="titlebar">
    <span class="name">
      <span class="icon16"><span></span><span></span><span></span><span></span></span>
      <span class="label">SPOTIDAL.EXE</span>
    </span>
    <span class="btns">
      <button id="help-btn" title="click any track for mix suggestions">?</button>
      <button id="noop-btn" title="nothing to see here">&times;</button>
    </span>
  </div>
  <div class="menubar">
    <div class="menu-item" id="mb-playlists">
      <span class="label">Playlists</span>
      <div class="submenu" id="mb-playlists-submenu"></div>
    </div>
    <div class="menu-item" id="mb-genres">
      <span class="label">Genres</span>
      <div class="submenu" id="mb-genres-submenu"></div>
    </div>
    <div class="menu-item" data-action="camelot">
      <span class="label">Camelot Wheel</span>
    </div>
  </div>
  <div id="body">
    <input id="q" class="field" type="text" placeholder="search title, artist, album..." autofocus>

    <fieldset id="filters-panel" class="open">
      <legend>filters</legend>
      <div class="filter-grid">
        <div>
          <label>artist</label>
          <input id="artist" class="field" type="text">
        </div>
        <div>
          <label>title</label>
          <input id="title" class="field" type="text">
        </div>
        <div>
          <label>playlist</label>
          <input id="playlist" class="field" type="text" list="playlist-options" placeholder="any">
          <datalist id="playlist-options"></datalist>
        </div>
        <div>
          <label>key</label>
          <input id="key" class="field" type="text" list="key-options" placeholder="any">
          <datalist id="key-options"></datalist>
        </div>
        <div>
          <label>genre</label>
          <input id="genre" class="field" type="text" list="genre-options" placeholder="any">
          <datalist id="genre-options"></datalist>
        </div>
        <div>
          <label>style</label>
          <input id="style" class="field" type="text" list="style-options" placeholder="any">
          <datalist id="style-options"></datalist>
        </div>
        <div class="span2">
          <label>bpm</label>
          <div class="bpm-slider">
            <input id="bpm_min_slider" type="range" min="40" max="220" value="40">
            <input id="bpm_max_slider" type="range" min="40" max="220" value="220">
          </div>
          <div class="bpm-slider-labels">
            <span id="bpm-min-label">40</span> &ndash; <span id="bpm-max-label">220</span> bpm
          </div>
        </div>
      </div>
    </fieldset>

    <div id="results" class="hidden">
      <table class="results-table" id="results-table">
        <thead>
          <tr>
            <th class="col-title" data-sort="title">Title<span class="arrow"></span></th>
            <th class="col-artist" data-sort="artist">Artist<span class="arrow"></span></th>
            <th class="col-album" data-sort="album">Album<span class="arrow"></span></th>
            <th class="col-genre" data-sort="genre">Genre<span class="arrow"></span></th>
            <th class="col-key" data-sort="key">Key<span class="arrow"></span></th>
            <th class="col-bpm" data-sort="bpm">BPM<span class="arrow"></span></th>
          </tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
    </div>

    <div id="taskbar">
      <div id="start-menu">
        <div class="menu-item" id="menu-playlists">
          <span class="swatch" style="background:#ffd400;"></span>
          <span class="label">Playlists</span>
          <span class="caret">&#9656;</span>
          <div class="submenu" id="playlists-submenu"></div>
        </div>
        <div class="menu-item" id="menu-genres">
          <span class="swatch" style="background:#00a0a0;"></span>
          <span class="label">Genres</span>
          <span class="caret">&#9656;</span>
          <div class="submenu" id="genres-submenu"></div>
        </div>
        <div class="menu-sep"></div>
        <div class="menu-item" data-action="camelot">
          <span class="swatch" style="background:#a000a0;"></span>
          <span class="label">Camelot Wheel</span>
        </div>
      </div>
      <button id="start-btn">
        <span class="icon16" style="width:16px;height:16px;"><span></span><span></span><span></span><span></span></span>
        Start
      </button>
      <button id="search-btn" title="jump to search">
        &#128269;
      </button>
    </div>
  </div>
  <div class="resize-handle" id="window-resize"></div>
</div>

<div id="dialog">
  <div class="titlebar">
    <span class="name">
      <span class="icon16"><span></span><span></span><span></span><span></span></span>
      <span class="label" id="dialog-title">DIALOG</span>
    </span>
    <span class="btns"><button id="dialog-close">&times;</button></span>
  </div>
  <div id="dialog-body"></div>
  <div class="resize-handle" id="dialog-resize"></div>
</div>

<script>
const $ = (id) => document.getElementById(id);
const state = {
  q: "", artist: "", title: "", playlist: "", genre: "", style: "", key: "",
  bpm_min: "", bpm_max: "",
};
let debounceTimer = null;
let knownPlaylists = [];
let knownGenres = [];
let knownStyles = [];
let knownKeys = [];
let lastTracks = [];
let sortKey = null;
let sortDir = 1;

function fmtBpm(bpm) { return bpm ? Math.round(bpm * 10) / 10 : ""; }

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function camelotColor(key) {
  const match = /^(\\d{1,2})([AB])$/.exec((key || "").toUpperCase());
  if (!match) return "#c0c0c0";
  const hue = (parseInt(match[1], 10) - 1) * 30;
  return `hsl(${hue}, 65%, 72%)`;
}

let topZ = 10;
function bringToFront(win) {
  topZ += 1;
  win.style.zIndex = topZ;
}

function makeDraggable(win, handle) {
  let dragging = false, startX, startY, startLeft, startTop;
  handle.addEventListener("mousedown", (e) => {
    if (e.target.closest("button")) return;
    dragging = true;
    bringToFront(win);
    const rect = win.getBoundingClientRect();
    startX = e.clientX; startY = e.clientY;
    startLeft = rect.left; startTop = rect.top;
    win.style.left = startLeft + "px";
    win.style.top = startTop + "px";
    document.body.style.userSelect = "none";
    e.preventDefault();
  });
  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    win.style.left = Math.max(0, startLeft + (e.clientX - startX)) + "px";
    win.style.top = Math.max(0, startTop + (e.clientY - startY)) + "px";
  });
  document.addEventListener("mouseup", () => {
    dragging = false;
    document.body.style.userSelect = "";
  });
}

function makeResizable(win, handle) {
  let resizing = false, startX, startY, startWidth, startHeight;
  handle.addEventListener("mousedown", (e) => {
    resizing = true;
    bringToFront(win);
    const rect = win.getBoundingClientRect();
    startX = e.clientX; startY = e.clientY;
    startWidth = rect.width; startHeight = rect.height;
    win.style.height = startHeight + "px";
    document.body.style.userSelect = "none";
    e.preventDefault();
    e.stopPropagation();
  });
  document.addEventListener("mousemove", (e) => {
    if (!resizing) return;
    win.style.width = Math.max(300, startWidth + (e.clientX - startX)) + "px";
    win.style.height = Math.max(220, startHeight + (e.clientY - startY)) + "px";
  });
  document.addEventListener("mouseup", () => {
    resizing = false;
    document.body.style.userSelect = "";
  });
}

function initBpmSlider() {
  const minSlider = $("bpm_min_slider");
  const maxSlider = $("bpm_max_slider");
  const bounds = { min: parseInt(minSlider.min, 10), max: parseInt(maxSlider.max, 10) };

  function apply() {
    const minV = parseInt(minSlider.value, 10);
    const maxV = parseInt(maxSlider.value, 10);
    $("bpm-min-label").textContent = minV;
    $("bpm-max-label").textContent = maxV;
    state.bpm_min = minV > bounds.min ? String(minV) : "";
    state.bpm_max = maxV < bounds.max ? String(maxV) : "";
    debouncedSearch();
  }

  minSlider.addEventListener("input", () => {
    if (parseInt(minSlider.value, 10) > parseInt(maxSlider.value, 10)) minSlider.value = maxSlider.value;
    apply();
  });
  maxSlider.addEventListener("input", () => {
    if (parseInt(maxSlider.value, 10) < parseInt(minSlider.value, 10)) maxSlider.value = minSlider.value;
    apply();
  });
}

async function loadOptions() {
  const res = await fetch("/api/options");
  const data = await res.json();
  knownPlaylists = data.playlists;
  knownGenres = data.genres;
  knownStyles = data.styles;
  knownKeys = data.keys;
  for (const [field, values] of Object.entries({
    playlist: data.playlists, genre: data.genres, style: data.styles, key: data.keys,
  })) {
    const datalist = $(field + "-options");
    for (const value of values) {
      const opt = document.createElement("option");
      opt.value = value;
      datalist.appendChild(opt);
    }
  }
}

function closeSubmenuTree(submenu) {
  submenu.classList.remove("open", "flip-left", "flip-up");
  submenu.querySelectorAll(".submenu.open").forEach((el) => el.classList.remove("open", "flip-left", "flip-up"));
}

function attachSubmenu(item, submenu) {
  let closeTimer = null;

  function openNow() {
    clearTimeout(closeTimer);
    // Close sibling branches at this level first, so navigating the tree
    // shows one open path at a time instead of every visited folder stacking.
    const siblingContainer = item.parentElement;
    siblingContainer.querySelectorAll(":scope > .menu-item > .submenu").forEach((sib) => {
      if (sib !== submenu) closeSubmenuTree(sib);
    });
    submenu.classList.add("open");
    // Position from the trigger's real screen location now that it's
    // visible and measurable, rather than relying on CSS left:100%.
    const itemRect = item.getBoundingClientRect();
    const subRect = submenu.getBoundingClientRect();
    let left = itemRect.right - 2;
    if (left + subRect.width > window.innerWidth - 4) {
      left = itemRect.left - subRect.width + 2;
    }
    left = Math.max(4, left);
    let top = itemRect.top - 2;
    if (top + subRect.height > window.innerHeight - 4) {
      top = Math.max(4, window.innerHeight - subRect.height - 4);
    }
    submenu.style.left = left + "px";
    submenu.style.top = top + "px";
  }

  function scheduleClose() {
    clearTimeout(closeTimer);
    // A grace period survives the diagonal mouse move from the item into its
    // flyout - without it, hover lost the pointer mid-crossing and the
    // submenu closed before it could be read or clicked.
    closeTimer = setTimeout(() => closeSubmenuTree(submenu), 350);
  }

  item.addEventListener("mouseenter", openNow);
  item.addEventListener("mouseleave", scheduleClose);
  submenu.addEventListener("mouseenter", () => clearTimeout(closeTimer));
  submenu.addEventListener("mouseleave", scheduleClose);
}

async function loadPlaylistTree() {
  const res = await fetch("/api/playlist-tree");
  const tree = await res.json();
  $("playlists-submenu").appendChild(renderPlaylistNode(tree));
  $("mb-playlists-submenu").appendChild(renderPlaylistNode(tree));
}

function renderPlaylistNode(node) {
  const container = document.createElement("div");
  const folderNames = Object.keys(node._folders || {}).sort((a, b) => a.localeCompare(b));
  for (const name of folderNames) {
    const item = document.createElement("div");
    item.className = "menu-item";
    item.innerHTML = `
      <span class="swatch" style="background:#c08000;"></span>
      <span class="label">${escapeHtml(name)}</span>
      <span class="caret">&#9656;</span>
    `;
    const submenu = document.createElement("div");
    submenu.className = "submenu";
    submenu.appendChild(renderPlaylistNode(node._folders[name]));
    item.appendChild(submenu);
    attachSubmenu(item, submenu);
    container.appendChild(item);
  }
  const items = [...(node._items || [])].sort((a, b) => a.name.localeCompare(b.name));
  for (const entry of items) {
    const item = document.createElement("div");
    item.className = "menu-item leaf";
    item.innerHTML = `<span class="swatch"></span><span class="label">${escapeHtml(entry.name)} (${entry.count})</span>`;
    item.addEventListener("click", (e) => {
      e.stopPropagation();
      openCollectionDialog("playlist", entry.name);
      closeStartMenu();
    });
    container.appendChild(item);
  }
  return container;
}

async function loadGenreMenu() {
  const res = await fetch("/api/genre-counts");
  const genres = await res.json();
  renderGenreList($("genres-submenu"), genres);
  renderGenreList($("mb-genres-submenu"), genres);
}

function renderGenreList(submenu, genres) {
  if (!genres.length) {
    submenu.innerHTML = '<div class="empty">none found</div>';
    return;
  }
  for (const entry of genres) {
    const item = document.createElement("div");
    item.className = "menu-item leaf";
    item.innerHTML = `<span class="swatch" style="background:#00c0c0;"></span><span class="label">${escapeHtml(entry.name)} (${entry.count})</span>`;
    item.addEventListener("click", (e) => {
      e.stopPropagation();
      openCollectionDialog("genre", entry.name);
      closeStartMenu();
    });
    submenu.appendChild(item);
  }
}

function hasActiveFilter() {
  return Object.values(state).some((value) => value !== "");
}

function openSuggestWindow(track) {
  const params = new URLSearchParams({
    track_id: track.track_id,
    title: track.title,
    artist: track.artist,
    bpm: track.bpm ?? "",
    key: track.key ?? "",
  });
  const width = 360, height = 480;
  const left = (window.screenX || window.screenLeft || 0) + (window.outerWidth || 400) + 10;
  const top = window.screenY || window.screenTop || 0;
  window.open(
    "/suggest?" + params.toString(),
    "spotidal-suggest-" + track.track_id,
    `width=${width},height=${height},left=${left},top=${top},menubar=no,toolbar=no,location=no,status=no,resizable=yes`
  );
}

// Shared row template for every track table (main results, playlist/genre/
// artist dialog): title, artist (clickable -> that artist's dialog), album,
// key, bpm; the row itself opens the track's mix-suggestions window.
function buildTrackRow(track) {
  const tr = document.createElement("tr");
  tr.className = "track-row";
  tr.dataset.trackId = track.track_id;
  const meta = [track.genre, track.style].filter(Boolean).join(" / ");
  tr.title = meta || "";
  tr.innerHTML = `
    <td class="col-title">${escapeHtml(track.title)}</td>
    <td class="col-artist"><span class="artist-link">${escapeHtml(track.artist)}</span></td>
    <td class="col-album">${escapeHtml(track.album || "")}</td>
    <td class="col-genre">${escapeHtml(meta)}</td>
    <td class="col-key">${escapeHtml(track.key || "")}</td>
    <td class="col-bpm">${fmtBpm(track.bpm)}</td>
  `;
  tr.addEventListener("click", () => openSuggestWindow(track));
  tr.querySelector(".artist-link").addEventListener("click", (e) => {
    e.stopPropagation();
    openCollectionDialog("artist", track.artist);
  });
  return tr;
}

function renderRows(tracks) {
  const rows = $("rows");
  rows.innerHTML = "";
  if (!tracks.length) {
    rows.innerHTML = '<tr><td colspan="6" class="empty">no tracks match</td></tr>';
    return;
  }
  for (const track of tracks) {
    const tr = buildTrackRow(track);
    rows.appendChild(tr);
  }
}

function sortAndRender() {
  let list = [...lastTracks];
  if (sortKey) {
    list.sort((a, b) => {
      let av = a[sortKey];
      let bv = b[sortKey];
      if (av == null) av = sortKey === "bpm" ? -Infinity : "";
      if (bv == null) bv = sortKey === "bpm" ? -Infinity : "";
      if (typeof av === "string") av = av.toLowerCase();
      if (typeof bv === "string") bv = bv.toLowerCase();
      if (av < bv) return -1 * sortDir;
      if (av > bv) return 1 * sortDir;
      return 0;
    });
  }
  renderRows(list);
}

function updateSortIndicators() {
  document.querySelectorAll("#results-table th[data-sort]").forEach((th) => {
    const active = th.dataset.sort === sortKey;
    th.querySelector(".arrow").textContent = active ? (sortDir === 1 ? "▲" : "▼") : "";
  });
}

document.querySelectorAll("#results-table th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (sortKey === key) sortDir *= -1;
    else { sortKey = key; sortDir = 1; }
    updateSortIndicators();
    sortAndRender();
  });
});

async function search() {
  const active = hasActiveFilter();
  $("results").classList.toggle("hidden", !active);
  if (!active) { lastTracks = []; return; }

  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.artist) params.set("artist", state.artist);
  if (state.title) params.set("title", state.title);
  if (state.playlist && knownPlaylists.includes(state.playlist)) params.set("playlist", state.playlist);
  if (state.genre && knownGenres.includes(state.genre)) params.set("genre", state.genre);
  if (state.style && knownStyles.includes(state.style)) params.set("style", state.style);
  if (state.key && knownKeys.includes(state.key)) params.set("key", state.key);
  if (state.bpm_min) params.set("bpm_min", state.bpm_min);
  if (state.bpm_max) params.set("bpm_max", state.bpm_max);

  const res = await fetch("/api/tracks?" + params.toString());
  lastTracks = await res.json();
  sortAndRender();
}

function debouncedSearch() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(search, 150);
}

function openDialog(title) {
  $("dialog-title").textContent = title;
  $("dialog-body").innerHTML = "";
  $("dialog").classList.add("open");
  bringToFront($("dialog"));
}

function closeDialog() {
  $("dialog").classList.remove("open");
}

async function openCollectionDialog(kind, name) {
  openDialog(name.toUpperCase());
  const body = $("dialog-body");
  body.innerHTML = `
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;">
      <select id="g-key" class="field" style="flex:1 1 80px;"><option value="">any key</option></select>
      <input id="g-bpm-min" class="field" type="number" placeholder="bpm min" style="flex:1 1 80px;">
      <input id="g-bpm-max" class="field" type="number" placeholder="bpm max" style="flex:1 1 80px;">
    </div>
    <div style="background:#fff;max-height:60vh;overflow-y:auto;border:2px inset var(--face);">
      <table class="results-table" id="g-table">
        <thead>
          <tr>
            <th class="col-title" data-sort="title">Title<span class="arrow"></span></th>
            <th class="col-artist" data-sort="artist">Artist<span class="arrow"></span></th>
            <th class="col-album" data-sort="album">Album<span class="arrow"></span></th>
            <th class="col-genre" data-sort="genre">Genre<span class="arrow"></span></th>
            <th class="col-key" data-sort="key">Key<span class="arrow"></span></th>
            <th class="col-bpm" data-sort="bpm">BPM<span class="arrow"></span></th>
          </tr>
        </thead>
        <tbody id="g-rows"><tr><td colspan="6" class="empty">loading...</td></tr></tbody>
      </table>
    </div>
  `;

  let all = [];
  let gSortKey = null;
  let gSortDir = 1;
  const gFilters = { key: "", bpm_min: "", bpm_max: "" };

  function render() {
    let list = all.filter((t) => {
      if (gFilters.key && t.key !== gFilters.key) return false;
      if (gFilters.bpm_min && (!t.bpm || t.bpm < parseFloat(gFilters.bpm_min))) return false;
      if (gFilters.bpm_max && (!t.bpm || t.bpm > parseFloat(gFilters.bpm_max))) return false;
      return true;
    });
    if (gSortKey) {
      list.sort((a, b) => {
        let av = a[gSortKey];
        let bv = b[gSortKey];
        if (av == null) av = gSortKey === "bpm" ? -Infinity : "";
        if (bv == null) bv = gSortKey === "bpm" ? -Infinity : "";
        if (typeof av === "string") av = av.toLowerCase();
        if (typeof bv === "string") bv = bv.toLowerCase();
        if (av < bv) return -1 * gSortDir;
        if (av > bv) return 1 * gSortDir;
        return 0;
      });
    }
    const rows = body.querySelector("#g-rows");
    rows.innerHTML = "";
    if (!list.length) {
      rows.innerHTML = '<tr><td colspan="6" class="empty">no matches</td></tr>';
      return;
    }
    for (const track of list) {
      rows.appendChild(buildTrackRow(track));
    }
  }

  body.querySelectorAll("#g-table th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (gSortKey === key) gSortDir *= -1;
      else { gSortKey = key; gSortDir = 1; }
      body.querySelectorAll("#g-table th[data-sort]").forEach((h) => {
        h.querySelector(".arrow").textContent = h.dataset.sort === gSortKey ? (gSortDir === 1 ? "▲" : "▼") : "";
      });
      render();
    });
  });
  body.querySelector("#g-key").addEventListener("change", (e) => { gFilters.key = e.target.value; render(); });
  body.querySelector("#g-bpm-min").addEventListener("input", (e) => { gFilters.bpm_min = e.target.value; render(); });
  body.querySelector("#g-bpm-max").addEventListener("input", (e) => { gFilters.bpm_max = e.target.value; render(); });

  const res = await fetch("/api/tracks?" + kind + "=" + encodeURIComponent(name) + "&limit=1000");
  all = await res.json();
  const keys = [...new Set(all.map((t) => t.key).filter(Boolean))].sort();
  const keySelect = body.querySelector("#g-key");
  for (const k of keys) {
    const opt = document.createElement("option");
    opt.value = k; opt.textContent = k;
    keySelect.appendChild(opt);
  }
  render();
}

function openCamelotDialog() {
  openDialog("CAMELOT WHEEL");
  const body = $("dialog-body");
  body.innerHTML = `
    <div class="camelot-label">minor (A)</div>
    <div class="camelot-grid" id="camelot-a"></div>
    <div class="camelot-label">major (B)</div>
    <div class="camelot-grid" id="camelot-b"></div>
    <div id="camelot-result" style="margin-top:10px;"></div>
  `;
  const gridA = body.querySelector("#camelot-a");
  const gridB = body.querySelector("#camelot-b");
  for (let n = 1; n <= 12; n++) {
    for (const [letter, grid] of [["A", gridA], ["B", gridB]]) {
      const key = n + letter;
      const cell = document.createElement("div");
      cell.className = "camelot-key";
      cell.dataset.key = key;
      cell.textContent = key;
      cell.style.background = camelotColor(key);
      cell.addEventListener("click", () => selectCamelotKey(key));
      grid.appendChild(cell);
    }
  }
  selectCamelotKey(state.key || "8A");
}

async function selectCamelotKey(key) {
  const res = await fetch("/api/camelot?key=" + encodeURIComponent(key));
  const data = await res.json();
  const related = new Set(data.related || []);
  document.querySelectorAll(".camelot-key").forEach((cell) => {
    const isSelected = cell.dataset.key === key;
    const isRelated = related.has(cell.dataset.key);
    cell.classList.toggle("selected", isSelected);
    cell.classList.toggle("related", isRelated);
    cell.classList.toggle("dim", !isSelected && !isRelated);
  });
  const container = $("dialog-body").querySelector("#camelot-result");
  if (!related.size) {
    container.innerHTML = '<div class="empty">invalid key</div>';
    return;
  }
  container.innerHTML = `<div style="margin-bottom:6px;color:var(--muted);">compatible with ${escapeHtml(key)} &mdash; click to filter by one:</div>`;
  const list = document.createElement("div");
  list.id = "sug-list";
  for (const relatedKey of [...related].sort()) {
    const row = document.createElement("div");
    row.className = "sug-row";
    row.style.borderLeft = `6px solid ${camelotColor(relatedKey)}`;
    row.innerHTML = `<div class="sug-title">${escapeHtml(relatedKey)}</div>`;
    row.addEventListener("click", () => {
      state.key = relatedKey;
      $("key").value = relatedKey;
      $("filters-panel").classList.add("open");
      search();
      closeDialog();
    });
    list.appendChild(row);
  }
  container.appendChild(list);
}

$("q").addEventListener("input", (e) => { state.q = e.target.value; debouncedSearch(); });
$("artist").addEventListener("input", (e) => { state.artist = e.target.value; debouncedSearch(); });
$("title").addEventListener("input", (e) => { state.title = e.target.value; debouncedSearch(); });
$("playlist").addEventListener("input", (e) => { state.playlist = e.target.value; debouncedSearch(); });
for (const id of ["genre", "style", "key"]) {
  $(id).addEventListener("input", (e) => { state[id] = e.target.value; debouncedSearch(); });
}
$("dialog-close").addEventListener("click", closeDialog);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDialog(); });

function closeStartMenu() {
  $("start-menu").classList.remove("open");
  $("start-btn").classList.remove("open");
  document.querySelectorAll(".submenu.open").forEach((el) => el.classList.remove("open"));
}

$("start-btn").addEventListener("click", (e) => {
  e.stopPropagation();
  $("start-menu").classList.toggle("open");
  $("start-btn").classList.toggle("open");
});
$("start-menu").addEventListener("click", (e) => e.stopPropagation());
document.addEventListener("click", closeStartMenu);

$("search-btn").addEventListener("click", () => {
  closeStartMenu();
  window.scrollTo({ top: 0, behavior: "smooth" });
  $("q").focus();
  $("q").select();
});

document.querySelectorAll(".menu-item[data-action]").forEach((item) => {
  item.addEventListener("click", () => {
    const action = item.dataset.action;
    closeStartMenu();
    if (action === "camelot") {
      openCamelotDialog();
    }
  });
});

attachSubmenu($("menu-playlists"), $("playlists-submenu"));
attachSubmenu($("menu-genres"), $("genres-submenu"));

const mainWindow = $("window");
mainWindow.style.left = "28px";
mainWindow.style.top = "30px";
// Without an explicit height, #window sizes to its content ("auto"), which
// defeats the inner flex:1/overflow:auto areas (results, sidebar) - they
// need a constrained parent to actually scroll instead of just growing it.
mainWindow.style.height = Math.max(320, Math.min(620, window.innerHeight - 80)) + "px";
makeDraggable(mainWindow, mainWindow.querySelector(".titlebar"));
makeDraggable($("dialog"), $("dialog").querySelector(".titlebar"));
makeResizable(mainWindow, $("window-resize"));
makeResizable($("dialog"), $("dialog-resize"));

attachSubmenu($("mb-playlists"), $("mb-playlists-submenu"));
attachSubmenu($("mb-genres"), $("mb-genres-submenu"));

loadOptions();
loadPlaylistTree();
loadGenreMenu();
initBpmSlider();
search();
</script>
</body>
</html>
"""
)


SUGGEST_PAGE_HTML = (
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>mix suggestions</title>
<style>
"""
    + _RETRO_CSS
    + """
  #window { width: 100%; }
  #results { display: block; }
  #filter-bar { display: flex; gap: 6px; padding: 6px 0 0; flex-wrap: wrap; }
  #filter-bar > * { flex: 1 1 80px; }
</style>
</head>
<body>

<div id="window">
  <div class="titlebar">
    <span class="name">
      <span class="icon16"><span></span><span></span><span></span><span></span></span>
      <span class="label" id="win-title">MIX SUGGESTIONS</span>
    </span>
    <span class="btns"><button id="close-btn">&times;</button></span>
  </div>
  <div id="body">
    <div id="seed-sub" style="margin-bottom:8px;color:var(--muted);"></div>
    <div id="filter-bar">
      <select id="f-genre" class="field"><option value="">any genre</option></select>
      <select id="f-key" class="field"><option value="">any key</option></select>
      <input id="f-bpm-min" class="field" type="number" placeholder="bpm min">
      <input id="f-bpm-max" class="field" type="number" placeholder="bpm max">
    </div>
    <div id="results" style="margin-top:8px;">
      <table class="results-table" id="results-table">
        <thead>
          <tr>
            <th class="col-title" data-sort="title">Title<span class="arrow"></span></th>
            <th class="col-artist" data-sort="artist">Artist<span class="arrow"></span></th>
            <th class="col-album" data-sort="album">Album<span class="arrow"></span></th>
            <th class="col-genre" data-sort="genre">Genre<span class="arrow"></span></th>
            <th class="col-key" data-sort="key">Key<span class="arrow"></span></th>
            <th class="col-bpm" data-sort="bpm">BPM<span class="arrow"></span></th>
          </tr>
        </thead>
        <tbody id="rows"><tr><td colspan="6" class="empty">loading...</td></tr></tbody>
      </table>
    </div>
    <div id="taskbar" style="justify-content:flex-end;">
      <span id="taskbar-status">loading...</span>
    </div>
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(window.location.search);
const seed = {
  track_id: params.get("track_id"),
  title: params.get("title") || "",
  artist: params.get("artist") || "",
  bpm: parseFloat(params.get("bpm")) || null,
  key: params.get("key") || "",
};
document.title = seed.title ? seed.title + " — mix suggestions" : "mix suggestions";
$("win-title").textContent = seed.title || "mix suggestions";
$("seed-sub").textContent = `${seed.artist}${seed.bpm ? " — " + seed.bpm + " bpm" : ""}${seed.key ? " — " + seed.key : ""}`;

let allSuggestions = [];
let sortKey = null;
let sortDir = 1;
const filters = { genre: "", key: "", bpm_min: "", bpm_max: "" };

function fmtBpm(bpm) { return bpm ? Math.round(bpm * 10) / 10 : ""; }
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function populateFilterOptions() {
  const genres = [...new Set(allSuggestions.map((t) => t.genre).filter(Boolean))].sort();
  const keys = [...new Set(allSuggestions.map((t) => t.key).filter(Boolean))].sort();
  for (const g of genres) {
    const opt = document.createElement("option");
    opt.value = g; opt.textContent = g;
    $("f-genre").appendChild(opt);
  }
  for (const k of keys) {
    const opt = document.createElement("option");
    opt.value = k; opt.textContent = k;
    $("f-key").appendChild(opt);
  }
}

function applyFiltersAndRender() {
  let list = allSuggestions.filter((t) => {
    if (filters.genre && t.genre !== filters.genre) return false;
    if (filters.key && t.key !== filters.key) return false;
    if (filters.bpm_min && (!t.bpm || t.bpm < parseFloat(filters.bpm_min))) return false;
    if (filters.bpm_max && (!t.bpm || t.bpm > parseFloat(filters.bpm_max))) return false;
    return true;
  });
  if (sortKey) {
    list.sort((a, b) => {
      let av = a[sortKey]; let bv = b[sortKey];
      if (av == null) av = sortKey === "bpm" ? -Infinity : "";
      if (bv == null) bv = sortKey === "bpm" ? -Infinity : "";
      if (typeof av === "string") av = av.toLowerCase();
      if (typeof bv === "string") bv = bv.toLowerCase();
      if (av < bv) return -1 * sortDir;
      if (av > bv) return 1 * sortDir;
      return 0;
    });
  }
  $("taskbar-status").textContent = `${list.length} of ${allSuggestions.length} suggestion(s)`;
  const rows = $("rows");
  rows.innerHTML = "";
  if (!list.length) {
    rows.innerHTML = '<tr><td colspan="6" class="empty">no matches</td></tr>';
    return;
  }
  for (const track of list) {
    const tr = document.createElement("tr");
    tr.className = "track-row";
    const meta = [track.genre, track.style].filter(Boolean).join(" / ");
    tr.title = meta || "";
    tr.innerHTML = `
      <td class="col-title">${escapeHtml(track.title)}</td>
      <td class="col-artist">${escapeHtml(track.artist)}</td>
      <td class="col-album">${escapeHtml(track.album || "")}</td>
      <td class="col-genre">${escapeHtml(meta)}</td>
      <td class="col-key">${escapeHtml(track.key || "")}</td>
      <td class="col-bpm">${fmtBpm(track.bpm)}</td>
    `;
    tr.addEventListener("click", () => openSuggestWindow(track));
    rows.appendChild(tr);
  }
}

function openSuggestWindow(track) {
  const p = new URLSearchParams({
    track_id: track.track_id, title: track.title, artist: track.artist,
    bpm: track.bpm ?? "", key: track.key ?? "",
  });
  const width = 360, height = 480;
  const left = (window.screenX || window.screenLeft || 0) + (window.outerWidth || 400) + 10;
  const top = window.screenY || window.screenTop || 0;
  window.open(
    "/suggest?" + p.toString(),
    "spotidal-suggest-" + track.track_id,
    `width=${width},height=${height},left=${left},top=${top},menubar=no,toolbar=no,location=no,status=no,resizable=yes`
  );
}

document.querySelectorAll("#results-table th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (sortKey === key) sortDir *= -1;
    else { sortKey = key; sortDir = 1; }
    document.querySelectorAll("#results-table th[data-sort]").forEach((h) => {
      h.querySelector(".arrow").textContent = h.dataset.sort === sortKey ? (sortDir === 1 ? "▲" : "▼") : "";
    });
    applyFiltersAndRender();
  });
});

$("f-genre").addEventListener("change", (e) => { filters.genre = e.target.value; applyFiltersAndRender(); });
$("f-key").addEventListener("change", (e) => { filters.key = e.target.value; applyFiltersAndRender(); });
$("f-bpm-min").addEventListener("input", (e) => { filters.bpm_min = e.target.value; applyFiltersAndRender(); });
$("f-bpm-max").addEventListener("input", (e) => { filters.bpm_max = e.target.value; applyFiltersAndRender(); });
$("close-btn").addEventListener("click", () => window.close());

(async function load() {
  const res = await fetch("/api/suggest?track_id=" + encodeURIComponent(seed.track_id));
  allSuggestions = await res.json();
  populateFilterOptions();
  applyFiltersAndRender();
})();
</script>
</body>
</html>
"""
)
