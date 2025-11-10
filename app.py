# npx jest tests/test_frontend/ --clearCache
# npx jest tests/test_frontend/
# set PYTHONPATH=. && pytest tests/test_backend/ -v

# grok's help with tests
# https://x.com/i/grok/share/YblEz7g5PzVRXsdzHRJ8pPI4v
# pyinstaller --onefile --add-data "templates;templates" app.py
# pyinstaller --onefile --add-data "templates;templates" --add-data "static;static" app.py
# IMPORTANT: 
#   leftSelected.path for copy src, hist: see tr.click()
#   rightSelected.slot for copy dst, used in savefile_names()
#   rightSelected.path for backup

# grok's read_saves cache - https://x.com/i/grok/share/ZR3ZiC1HC1yH0KyAYAcZCsTmk

import concurrent.futures
from flask import Flask, render_template, jsonify, request, send_file
from pathlib import Path
from itertools import groupby
from operator import itemgetter
from pprint import pprint
import sys
import os
import re
import json
import shutil
import datetime
import inspect
lno = lambda: f'{inspect.stack()[1].lineno:04d}'
import hgdecomp as hg
# Load config at module level (runs once on import)
from settings import load_config  # Import the new config loader

import logging
from logging.handlers import RotatingFileHandler

# Force UTF-8 on stdout/stderr early (before any logging)
if sys.platform.startswith('win') and sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
else:
    # Non-Windows or older Python: Set encoding if possible
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
        sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')

# Log format
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Root logger setup (no basicConfig to avoid auto-handler)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Remove any existing handlers to start clean (avoids duplicates from basicConfig if run multiple times)
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Console handler (uses reopened UTF-8 stream)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(log_format))
root_logger.addHandler(console_handler)

# File handler with explicit UTF-8 (rotating)
file_handler = RotatingFileHandler(
    'nms_saves_manager.log', 
    maxBytes=10*1024*1024, 
    backupCount=5,
    encoding='utf-8'  # Explicit UTF-8 for file
)
file_handler.setLevel(logging.DEBUG)  # More verbose in file
file_handler.setFormatter(logging.Formatter(log_format))
root_logger.addHandler(file_handler)

# Capture Flask/Werkzeug startup (now uses our handlers)
logging.getLogger('werkzeug').setLevel(logging.INFO)

# App-specific logger (inherits from root)
logger = logging.getLogger(__name__)
# ... (rest of your config)

config_data = load_config()
MODE = config_data['MODE']
GAME_SAVES_DIR = Path(config_data['GAME_SAVES_DIR'])
POOL_DIR       = Path(f"NMS_{config_data['MODE'].capitalize()}_Pool")
POOL_REGEX = re.compile(r'^(?P<slot>\d{2})_(?P<mtime>\d{8}\-\d{6})_(?P<runtime>\d{4,6})_(?P<savename>.+)$')
SAFE_TITLE = re.compile(r'[^a-zA-Z0-9#]+')
TIME_LEDGER = {}
POOL_HEALTH_CHECK = True

if not config_data['hg']: 
    logger.error("Either edit your config.json or delete it, then run again")
    sys.exit(1)
logger.info(f"MODE: {config_data['MODE']}, GAME_SAVES_DIR: {GAME_SAVES_DIR}")

app = Flask(__name__)

# helper: expected save filenames for a slot
def savefile_names(slot: int):
    """
    Generates the four expected .hg filenames for a given NMS save slot (1-15).
    Includes main save, restore point, and variants (e.g., mf_save2.hg, save2.hg for slot 1).
    
    Args:
        slot (int): Save slot number (1-15).
    
    Returns:
        list[str]: List of filenames (e.g., ['mf_save.hg', 'save.hg', 'mf_save2.hg', 'save2.hg'] for slot 1).
    
    Example:
        >>> savefile_names(9)
        ['mf_save18.hg', 'save18.hg', 'mf_save16.hg', 'save16.hg']
    """
    names = []
    for i in [-1, 0]:
        n = slot * 2 + i
        n = n if n != 1 else ""
        names.append(f"mf_save{n}.hg")
        names.append(f"save{n}.hg")
    return names

# Usage - uncomment print() at 102 in 'hg' if you're looking for more keys than {'<h0', '6f='}
# ver = 4708 # save30.hg
# print(f"ver= {ver} {hg.v(ver)}")
# slot = 9
# print(f'slot= {slot}, savefile_names= {savefile_names(slot)}')
# print(extract_pk4_lg8('save14.hg'))
# save_vers, common_key, total_time, save_name = hg.extract_pk4_lg8('save26.hg')
# print(f"Save Name: {save_name} Play Time: {total_time} key: '{common_key}' Version: {save_vers} {hg.v(save_vers)}")
# quit()

# def read_saves(d: Path):
#     """
#     Scans the game saves directory for .hg files, extracting metadata for even-numbered saves (restore points).
#     Computes slot (1-15), mtime (YYYYMMDD-HHMMSS), runtime (HHMM), sanitized savename, and display path.
#     Only processes files matching 'save<even>.hg'.
    
#     Args:
#         d (Path): Directory path (GAME_SAVES_DIR).
    
#     Returns:
#         list[dict]: List of save dicts with keys: slot, mtime, runtime, savename, path.
    
#     Note:
#         Skips odd-numbered saves and non-matching files; uses extract_pk4_lg8 for metadata.
#     """
#     out = []
#     # print(f"d= {d}")
#     if not d.exists():
#         return out
#     for p in d.iterdir():
#         # print(f"p= {p}")
#         if p.is_file():
#             m = re.match(r'save(\d+).hg$', str(p.name)) # this kicks out save.hg and odd numbers, only pick Restore Point saves
#             if m and int(m.group(1)) % 2 == 0:
#                 slot = int(m.group(1)) // 2
#                 mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y%m%d-%H%M%S")

#                 save_vers, common_key, total_time, save_name = hg.extract_pk4_lg8(p)
#                 runtime = f"{total_time // 3600:02d}{(total_time % 3600) // 60:02d}"
#                 safetitle = re.sub(SAFE_TITLE, "-", save_name) if save_name else "Unnamed-Save" # Sanitize for dir name
#                 savepath = f"{slot:02d}_{mtime}_{runtime}_{safetitle}"

#                 out.append(dict(slot=slot,
#                                 mtime=mtime,
#                                 runtime=runtime, 
#                                 savename=safetitle[:30],
#                                 path=savepath))

#     out = sorted(out, key=lambda x: x['slot'])
#     # with open("read_saves.json", "w") as f:
#     #     json.dump(out, f, indent=4)

#     return out

# Simple per-file cache (clears on restart; no globals beyond this dict)

SAVES_PARSE_CACHE = {}  # Key: (file_path, mtime_float, size) -> {'runtime': str, 'savename': str, 'mtime_str': str, 'savepath': str}

def _get_file_fingerprint(file_path: str) -> tuple:
    """(path, mtime, size) – mtime as float for sub-sec precision."""
    p = Path(file_path)
    if not p.exists():
        return (file_path, None, None)
    stat = p.stat()
    return (file_path, stat.st_mtime, stat.st_size)

def read_saves(d: Path):
    """
    Refresh-only: Stat all even .hg on every call (fast).
    Parse only if fingerprint changed (decompress/JSON).
    No global list cache – always rebuilds fresh list (negligible overhead).
    """
    if not d.exists():
        return []
    
    out = []
    even_save_files = []
    for p in d.iterdir():
        if p.is_file():
            m = re.match(r'save(\d+).hg$', str(p.name))
            if m and int(m.group(1)) % 2 == 0:
                slot = int(m.group(1)) // 2
                file_path = str(p)
                even_save_files.append((slot, file_path))
    
    # Parallel: Stat + selective parse
    def process_slot(slot_file):
        slot, file_path = slot_file
        fp = _get_file_fingerprint(file_path)
        if fp[1] is None:  # File gone
            return dict(slot=slot, mtime='', runtime='', savename='', path='')
        
        if fp in SAVES_PARSE_CACHE:
            logger.debug(f"Cache hit for {file_path}")
            cached = SAVES_PARSE_CACHE[fp]
        else:
            logger.debug(f"Parsing changed {file_path}")
            try:
                save_vers, common_key, total_time, save_name = hg.extract_pk4_lg8(file_path)
                mtime_str = datetime.datetime.fromtimestamp(fp[1]).strftime("%Y%m%d-%H%M%S")
                runtime = f"{total_time // 3600:02d}{(total_time % 3600) // 60:02d}" if total_time else ''
                safetitle = re.sub(SAFE_TITLE, "-", save_name) if save_name else "Unnamed-Save"
                savename = safetitle[:30]
                savepath = f"{slot:02d}_{mtime_str}_{runtime}_{savename}"
                cached = {'mtime': mtime_str, 'runtime': runtime, 'savename': savename, 'savepath': savepath}
                SAVES_PARSE_CACHE[fp] = cached
            except Exception as e:
                logger.warning(f"Parse failed: {e}")
                return dict(slot=slot, mtime='', runtime='', savename='', path='')
        
        return dict(slot=slot, mtime=cached['mtime'], runtime=cached['runtime'], savename=cached['savename'], path=cached['savepath'])
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(even_save_files))) as executor:
        futures = [executor.submit(process_slot, sf) for sf in even_save_files]
        out = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    return sorted(out, key=lambda x: x['slot'])

def read_pool(pool_dir: Path):
    """
    Reads pool directory entries, matching the POOL_REGEX for slot_mtime_runtime_savename dirs.
    Returns list of dicts with slot (int), mtime, runtime, savename, path.
    Sorts by filename (natural order).
    
    Args:
        pool_dir (Path): POOL_DIR path.
    
    Returns:
        list[dict]: Pool entries; raises Exception on regex mismatch.
    
    Note:
        Assumes all subdirs match regex; no filtering for files.
    """
    global TIME_LEDGER
    TIME_LEDGER = {}
    entries = []
    if not pool_dir.exists():
        return entries

    for p in sorted(pool_dir.iterdir()):
        if p.is_dir():
            name = p.name
            # print(name)
            m = POOL_REGEX.match(name)
            if m:
                d = m.groupdict()
                entries.append({ **d, 'slot': int(d['slot']), 'path': name })

                if d['mtime'] in TIME_LEDGER:
                    TIME_LEDGER[d['mtime']].append(int(d['slot']))
                else:
                    TIME_LEDGER[d['mtime']] = [int(d['slot'])]
            else:
                entries.append({ 'slot': 0, 'path': '', 'mtime': '', 'runtime': '', 'savename': '', 'path': name })
                logger.warning(f"{lno()} POOL_REGEX.match failed for: {name}")

    # with open("read_pool.json", "w") as f:
    #     json.dump(entries, f, indent=4)

    return entries

@app.route('/')
def index():
    """
    Serves the main NMS Save Manager HTML template.
    
    Returns:
        Response: Rendered 'index.html'.
    """
    return render_template('index.html', mode=MODE)

@app.route('/api/saves')
def api_saves():
    """
    API endpoint: Lists active saves from GAME_SAVES_DIR via read_saves().
    
    Returns:
        JSON: List of save dicts (slot, mtime, runtime, savename, path).
    """
    # list files in GAME_SAVES_DIR
    saves = read_saves(GAME_SAVES_DIR)
    return jsonify(saves)

@app.route('/api/pool')
def api_pool(): # TODO verify sjh
    """
    API endpoint: Lists most current pool entry per slot from POOL_DIR.
    Filters to one per slot, adds 'note' flag if note.txt exists.
    
    Returns:
        JSON: List of pool dicts (slot, mtime, runtime, savename, path, note: bool).
    """
    pool = read_pool(POOL_DIR)
    by_slot = {}
    for e in pool:
        by_slot[e['slot']] = e
    pool = list(by_slot.values())
    pool = [{**e, 'note': (POOL_DIR / e['path'] / 'note.txt').exists()} for e in pool]
    return jsonify({'pool': pool, 'ledger': TIME_LEDGER})

@app.route('/api/history/<int:slot>')
def api_history(slot):
    """
    API endpoint: Lists all historical pool entries for a specific slot.
    Filters read_pool() by slot, adds 'note' flag, sorts by mtime descending.
    
    Args:
        slot (int): Slot number (1-15).
    
    Returns:
        JSON: List of history dicts (sorted newest first).
    """
    pool = read_pool(POOL_DIR)
    hist = [p for p in pool if p.get('slot')==slot]
    hist = [{**e, 'note': (POOL_DIR / e['path'] / 'note.txt').exists()} for e in hist]
    return jsonify({'pool': sorted(hist, key=lambda x: x['mtime'], reverse=True), 'ledger': TIME_LEDGER})

def toPool(slot: int, path: str, saves_dir: Path = GAME_SAVES_DIR):
    """
    Copies a full 4-file NMS save slot into the pool directory.
    Returns jsonify() response directly.
    """
    logger.info(f'{lno()} Entering toPool ...')
    try:
        # Check the Saves 4-file set is complete
        missing = [f for f in savefile_names(slot) if not (saves_dir / f).exists()]
        if missing:
            logger.info(f'{lno()} {dict(ok=False, backup=False, error=f"Missing required files: {missing}", color="alert-danger", rc=400)}')
            return jsonify(dict(ok=False, backup=False, error=f"Missing required files: {missing}", color='alert-danger')), 400

        # Parse and validate pool path
        m = POOL_REGEX.match(path)
        if not m:
            logger.info(f'{lno()} {dict(ok=False, backup=False, error="Invalid pool path format", color="alert-danger", rc=400)}')
            return jsonify(dict(ok=False, backup=False, error="Invalid pool path format", color='alert-danger')), 400


        d = m.groupdict()
        # Prevent duplicates by mtime
        if d['mtime'] in TIME_LEDGER:
            slots = ",".join(map(str, TIME_LEDGER[d['mtime']]))
            logger.info(f'{lno()} {dict(ok=True, backup=False, content=f"Pool backup already exists in slot(s) {slots}", color="alert-info")}')
            return jsonify(dict(ok=True, backup=False, content=f"Pool backup already exists in slot(s) {slots}", color='alert-info')), 200

        # POOL_DIR is the parent and path is the child.
        new_dir = POOL_DIR / path
        new_dir.mkdir(parents=True, exist_ok=True)

        TIME_LEDGER[d['mtime']] = [d['slot']]
        for fname in savefile_names(slot):
            src = saves_dir / fname
            dst = new_dir / fname
            shutil.copy2(src, dst)
            logger.info(f'{lno()} [POOL] {src} → {dst}')

        logger.info(f'{lno()} {dict(ok=True, backup=True, content=f"Backed up to {path}", color="alert-success")}')
        return jsonify(dict(ok=True, backup=True, content=f"Backed up to {path}", color='alert-success')), 200
    except Exception as e:
        logger.error(f'{lno()} {dict(ok=False, error=str(e), color="alert-danger", rc=500)}')
        return jsonify(dict(ok=False, error=str(e), color='alert-danger')), 500

# def toSaves(src_slot: int, src_path: str, dst_slot: int, dst_path: int, auto_backup=True):
def toSaves(data: dict): # , auto_backup=True):
    """
    Copies a pool entry to a saves slot.
    Optionally auto-backs up the slot before overwrite.
    Returns jsonify() response directly.
    """
    logger.info(f'{lno()} Entering toSaves ...')
    try:
        src_slot, src_path, dst_slot, dst_path = itemgetter('src_slot', 'src_path', 'dst_slot', 'dst_path')(data)
        backup_taken = False

        # does the Pool path exists
        src_dir = POOL_DIR / src_path
        if not src_dir.exists():
            logger.info(f'{lno()} {dict(ok=False, error=f"Pool path not found: {src_path}", color="alert-danger", rc=404)}')
            return jsonify(dict(ok=False, error=f"Pool path not found: {src_path}", color='alert-danger')), 404

        # Check the Pool 4-file set is complete
        missing = [f for f in savefile_names(src_slot) if not (src_dir / f).exists()]
        if missing:
            logger.info(f'{lno()} {dict(ok=False, error=f"Pool missing required files: {missing}", color="alert-danger", rc=404)}')
            return jsonify(dict(ok=False, error=f"Pool missing required files: {missing}", color='alert-danger')), 400

        # is the Saves dst slot currently occupied
        target_files = [GAME_SAVES_DIR / name for name in savefile_names(dst_slot)]
        is_occupied = any(f.exists() for f in target_files)
        logger.info(f'{lno()} Saves slot is_occupied={is_occupied}')    

        # Auto-backup the dst Saves slot before overwriting
        if is_occupied:
            response, rc = toPool(dst_slot, dst_path)
            backup_taken = response.json['backup']
            if backup_taken:
                logger.info(f'{lno()} [AUTO BACKUP] Slot {dst_slot} → {dst_path}')

        src_files = [src_dir / f for f in savefile_names(src_slot)]
        for src_file, dst_file in zip(sorted(src_files), sorted(target_files)):
            shutil.copy2(src_file, dst_file)
            logger.info(f'{lno()} [TO SAVES] {src_file.name} → {dst_file}')

        # msg = f"Copied Pool '{src_path}' to Saves slot {dst_slot}" + " (auto-backup taken)" if backup_taken else ""
        logger.info(f'{lno()} {dict(ok=True, backup=backup_taken, content=f"Copied Pool {src_path} to Saves slot {dst_slot}", color="alert-success")}')
        return jsonify(dict(ok=True, backup=backup_taken, content=f"Copied Pool {src_path} to Saves slot {dst_slot}", color='alert-success'))

    except Exception as e:
        logger.info(dict(ok=False, error=str(e), color='alert-danger', rc=500))
        return jsonify(dict(ok=False, error=str(e), color='alert-danger')), 500

@app.route('/api/backup', methods=['POST'])
def api_backup():
    logger.info(f'{lno()} Entering api_backup ...')
    data = request.json or {}
    logger.info(f'{lno()} data= {data}')
    return toPool(data.get('slot'), data.get('path'))


@app.route('/api/copy', methods=['POST'])
def api_copy():
    logger.info(f'{lno()} Entering api_copy ...')
    data = request.json or {}
    logger.info(f'{lno()} data= {data}')
    return toSaves(data)
    # return toSaves(data.get('src_slot'), data.get('src_path'), data.get('dst_slot'), data.get('src_path'))


@app.route('/api/delete', methods=['POST'])
def api_delete():
    logger.info(f'{lno()} Entering api_delete ...')
    data = request.json or {}
    logger.info(f'{lno()} data= {data}')
    pool_path, saves_slot, saves_path, hist_selected = itemgetter('pool_path', 'saves_slot', 'saves_path', 'hist_selected')(data)
    backup_note = False

    try:
        # Delete from pool
        if pool_path:
            target = POOL_DIR / pool_path
            if target.is_dir():
                shutil.rmtree(target)
                logger.info(f'{lno()} {dict(ok=True, right=False, backup=False, content=f"Deleted pool {pool_path}")}')
                return jsonify(dict(ok=True, right=False, backup=False, content=f"Deleted pool {pool_path}"))
            logger.info(f'{lno()} {dict(ok=False, error="Pool path not found", rc=404)}')
            return jsonify(dict(ok=False, error="Pool path not found")), 404

        # Delete from saves
        if saves_slot:
            # Optionally backup before deletion
            response, rc = toPool(saves_slot, saves_path)
            logger.info(f'{lno()} toPool: response: {response.json}, rc: {rc}')
            backup_taken = response.json['backup']
            if backup_taken:                                      #  ?????????????????????            backup = True if back already exists ?!
                logger.info(f'{lno()} [AUTO BACKUP] Slot {saves_slot} → {pool_path}')

            for f in savefile_names(saves_slot):
                p = GAME_SAVES_DIR / f
                if p.exists():
                    p.unlink()
            logger.info(f'{lno()} {dict(ok=True, right=True, backup=backup_taken ,content=f"Saves slot {saves_slot} deleted")}')
            return jsonify(dict(ok=True, right=True, backup=backup_taken ,content=f"Saves slot {saves_slot} deleted"))

        logger.info(f'{lno()} {dict(ok=False, error="Nothing to delete", rc=400)}')
        return jsonify(dict(ok=False, error="Nothing to delete")), 400 # should this ever return?
    except Exception as e:
        logger.info(f'{lno()} {dict(ok=False, error=str(e), rc=500)}')
        return jsonify(dict(ok=False, error=str(e))), 500

@app.route('/api/note', methods=['GET', 'POST', 'DELETE'])
def api_note():
    """
    API endpoint: Handles note.txt CRUD for pool paths.
    
    GET: {path: str} -> {ok: bool, content: str}
    POST: {path: str, content: str} -> {ok: bool}
    DELETE: {path: str} -> {ok: bool}
    
    Notes are stored as UTF-8 text files in <pool_path>/note.txt.
    """
    if request.method == 'GET':
        # Your existing GET handler...
        data = request.args or {}
        path = data.get('path')
        if not path:
            return jsonify(dict(ok=False, error="missing path")), 400
        try:
            note_file = POOL_DIR / path / "note.txt"
            content = note_file.read_text(encoding='utf-8') if note_file.exists() else ""
            return jsonify(dict(ok=True, content=content))
        except Exception as e:
            return jsonify(dict(ok=False, error=str(e))), 500

    elif request.method == 'POST':
        # Your existing POST handler...
        data = request.json or {}
        path = data.get('path')
        content = data.get('content', '')
        if not path:
            return jsonify(dict(ok=False, error="missing path")), 400
        try:
            note_file = POOL_DIR / path / "note.txt"
            note_file.parent.mkdir(parents=True, exist_ok=True)
            note_file.write_text(content, encoding='utf-8')
            return jsonify(dict(ok=True))
        except Exception as e:
            return jsonify(dict(ok=False, error=str(e))), 500

    elif request.method == 'DELETE':
        data = request.json or {}
        path = data.get('path')
        if not path:
            return jsonify(dict(ok=False, error="missing path")), 400
        try:
            note_file = POOL_DIR / path / "note.txt"
            if note_file.exists():
                note_file.unlink()  # Delete the file
            return jsonify(dict(ok=True))
        except Exception as e:
            return jsonify(dict(ok=False, error=str(e))), 500

import subprocess  # Add this import at the top with others

import os  # Add at top if missing

@app.route('/slideshow')
def slideshow():
    """
    Serves the NMS slideshow page.
    """
    return render_template('slideshow.html')

@app.route('/api/slideshow-data')
def slideshow_data():
    """
    Dynamic: Lists .png/.jpg files in static/images/, returns {filename: description} JSON.
    Descriptions: Empty for now; customize below (e.g., from filename or a dict).
    """
    images_dir = os.path.join(app.static_folder, 'images')  # Resolves to ./static/images/
    if not os.path.exists(images_dir):
        return jsonify({})  # Empty if no dir

    # List and sort files (e.g., alphanumeric for Screenshot-0.png first)
    image_files = [f for f in os.listdir(images_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    # image_files.sort()  # Natural order: Screenshot-0.png, Screenshot-1.png, etc.
    print(image_files)

    # Build JSON: { "images/filename.png": "Description~with~breaks" }
    data = {}
    desc_map = {  # Optional: Hardcode descs by index/filename; expand as needed
        'Screenshot-0.png': 'Description for slide 0~Line 2',
        'Screenshot-11.png': 'Your slide 11 desc~With breaks',
        # Add more, or derive: e.g., data[f] = f.split('-')[1] if '-' in f else ''
    }
    for i, filename in enumerate(image_files):
        key = f"images/{filename}"
        data[key] = desc_map.get(filename, f"Slide {i}")  # Fallback to index if no custom desc

    return jsonify({"images/"+f:" " for f in image_files})

@app.route('/api/robo', methods=['POST'])
def api_robo():
    """
    API endpoint: Runs NMSrobocopy.bat via subprocess, passing GAME_SAVES_DIR as arg.
    Captures stdout/stderr for feedback; returns success/error.
    
    POST Body: {} (empty; extend as needed)
    
    Returns:
        JSON: {ok: bool, content: str (output), error: str, color: str}
    """
    data = request.json or {}
    msg = data.get('msg').strip().replace(" ", "-")
    msg = re.sub(SAFE_TITLE, "-", msg) if msg else "" # Sanitize for dir name
    try:
        result = subprocess.run(
            ['cmd.exe', '/c', 'NMSrobocopy.bat', str(GAME_SAVES_DIR), msg],  # Pass dir as %1 in bat
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))  # Run in app dir; adjust if needed
        )
        output = result.stdout.strip() if result.stdout else ''
        error = result.stderr.strip() if result.stderr else None
        print(output)
        
        if result.returncode > 1:
            return jsonify(dict(ok=False, error=f"Robocopy failed (code {result.returncode}): {error or output}", color='alert-danger'))
        else:
            return jsonify(dict(ok=True, content=f"Robocopy complete", color='alert-success'))
    except FileNotFoundError:
        return jsonify(dict(ok=False, error="NMSrobocopy.bat not found", color='alert-danger'))
    except Exception as e:
        return jsonify(dict(ok=False, error=str(e), color='alert-danger'))

@app.route('/api/build', methods=['POST'])
def api_build():
    dev = True
    backup_path = Path('.' if dev else r"D:\Downloads\No Man's Sky\backup")
    backup_dirs = [b for b in backup_path.iterdir() if b.is_dir() and re.match(r'^\d{8}-\d{6}', b.name)]
    # pprint(backup_dirs)
    results = []
    for b in backup_dirs:
        print("robo=", b)
        saves = read_saves(b if dev else b / STEAM_ID)
        # print('saves=',saves)

        for s in saves:
            print("   s=", s) # s['path'])
            # Check the Saves slot 4-file set is complete
            missing = [f for f in savefile_names(s['slot']) if not (b / f).exists()]
            if missing:
                logger.info(f"Missing: {s['slot']} {b}")
            else:
                response, rc = toPool(s['slot'], s['path'], b)

        archive = Path(f"archive")
        archive.mkdir(parents=True, exist_ok=True)
        if dev: shutil.move(b, archive)

    return jsonify(dict(ok=True, content="Pool extend complete"))

#-------------------------------------------------#
#                POOL_HEALTH_CHECK                #
#-------------------------------------------------#
fatal_error = False
entries = read_pool(POOL_DIR)
TIME_LEDGER = {}
for e in entries:
    m = POOL_REGEX.match(e['path'])
    if m:
        d = m.groupdict()
        # print(d)
        slot = int(d['slot'])
        path = Path(e['path'])
        note_count = 1 if (POOL_DIR / path / "note.txt").exists() else 0
        if note_count: print(f"{e['path']:40}: note")
        save_count = sum(1 for f in savefile_names(slot) if (POOL_DIR / path / f).exists())
        path_count = os.listdir(POOL_DIR / e['path'])

        if not re.match(r'^[a-zA-Z0-9#-]+$', d['savename']):
            print(f"{e['path']:40}: name failed safety check") 
            fatal_error = True

        if d['mtime'] in TIME_LEDGER:
            TIME_LEDGER[d['mtime']].append(int(d['slot']))
            print(f"{e['path']:40}: dup mtime:{TIME_LEDGER[d['mtime']]} (not fatal)")
        else:
            TIME_LEDGER[d['mtime']] = [int(d['slot'])]

        if save_count != 4 or len(path_count) != save_count + note_count:
            print(f"{e['path']:40}: wrong files in pool\n  {path_count} files:{len(path_count)} valid:{save_count} note:{note_count}")
            # print(len(path_count), save_count, note_count)
            fatal_error = True

    else:
        print(f"FATAL: POOL_REGEX.match({e['path']})")
        fatal_error = True

POOL_HEALTH_CHECK = False
if fatal_error:
    print(f"FATAL ERROR detected!")
    sys.exit(1)

if __name__ == '__main__':
    app.run(debug=True if MODE=='dev' else False, host='0.0.0.0', port=5000)