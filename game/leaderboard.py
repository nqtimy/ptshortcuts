"""Local and online (Supabase) leaderboard logic.

Local scores are stored in save.json under '_highscores'.
Online scores use Supabase REST API via urllib (no external dependencies).

Supabase config: supabase_config.json next to the exe (or project root in dev).
Expected schema:
  table 'scores': id (auto), pseudo text, cert text, difficulty int,
                  score int, created_at timestamptz (default now())
"""

import json
import os
import sys
import threading
import time
from datetime import date
from urllib.request import urlopen, Request
from urllib.error import URLError


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _config_path():
    # When bundled, check embedded files first (_MEIPASS), then next to exe as override.
    if getattr(sys, '_MEIPASS', None):
        embedded = os.path.join(sys._MEIPASS, 'supabase_config.json')
        if os.path.exists(embedded):
            return embedded
        return os.path.join(os.path.dirname(sys.executable), 'supabase_config.json')
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'supabase_config.json')


def load_config():
    """Return {'url': ..., 'anon_key': ...} or None if not configured."""
    try:
        with open(_config_path(), 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        if cfg.get('url') and cfg.get('anon_key'):
            return cfg
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return None


# ---------------------------------------------------------------------------
# Local high-scores (save.json → '_highscores')
# ---------------------------------------------------------------------------

from game.state import get_save_path


def _hs_key(cert, difficulty):
    return f"{cert}_{difficulty}"


def load_local_highscores():
    """Return full highscores dict from save.json."""
    from game.state import load_game
    return load_game().get('_highscores', {})


def get_local_best(cert, difficulty):
    """Return best local entry {score, pseudo, date} or None."""
    return load_local_highscores().get(_hs_key(cert, difficulty))


def save_local_highscore(cert, difficulty, score, pseudo):
    """Persist a new high-score entry if it beats the existing one.

    Returns True if it's a new record, False otherwise.
    """
    from game.state import load_game, save_game
    saved = load_game()
    hs = saved.setdefault('_highscores', {})
    key = _hs_key(cert, difficulty)
    existing = hs.get(key, {})
    if score > existing.get('score', -1):
        hs[key] = {
            'score': score,
            'pseudo': pseudo or 'Anonyme',
            'date': date.today().isoformat(),
        }
        save_game(saved)
        return True
    return False


# ---------------------------------------------------------------------------
# Pending sync queue (offline-first)
# ---------------------------------------------------------------------------

def _load_pending():
    from game.state import load_game
    return load_game().get('_pending_scores', [])


def _save_pending(pending):
    from game.state import load_game, save_game
    saved = load_game()
    saved['_pending_scores'] = pending
    save_game(saved)


def _add_pending(cert, difficulty, score, pseudo):
    pending = _load_pending()
    pending.append({
        'cert': cert,
        'difficulty': difficulty,
        'score': score,
        'pseudo': pseudo or 'Anonyme',
        'date': date.today().isoformat(),
    })
    _save_pending(pending)


# ---------------------------------------------------------------------------
# Supabase REST helpers
# ---------------------------------------------------------------------------

def _supabase_headers(cfg):
    return {
        'apikey': cfg['anon_key'],
        'Authorization': f"Bearer {cfg['anon_key']}",
        'Content-Type': 'application/json',
    }


def _post_score(cfg, cert, difficulty, score, pseudo):
    """POST a single score entry to Supabase. Raises on error."""
    url = cfg['url'].rstrip('/') + '/rest/v1/scores'
    payload = json.dumps({
        'pseudo': pseudo or 'Anonyme',
        'cert': cert,
        'difficulty': difficulty,
        'score': score,
    }).encode('utf-8')
    headers = {**_supabase_headers(cfg), 'Prefer': 'return=minimal'}
    req = Request(url, data=payload, headers=headers, method='POST')
    with urlopen(req, timeout=8) as resp:
        resp.read()


def fetch_online_scores(cert, difficulty, limit=10):
    """Fetch top scores from Supabase. Returns list of dicts or [] on error."""
    cfg = load_config()
    if not cfg:
        return []
    try:
        url = (cfg['url'].rstrip('/') +
               f"/rest/v1/scores"
               f"?cert=eq.{cert}&difficulty=eq.{difficulty}"
               f"&order=score.desc&limit={limit}"
               f"&select=pseudo,score,created_at")
        req = Request(url, headers=_supabase_headers(cfg))
        with urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except (URLError, json.JSONDecodeError, KeyError, OSError):
        return []


# ---------------------------------------------------------------------------
# Public async API (fire-and-forget threads)
# ---------------------------------------------------------------------------

def submit_score_async(cert, difficulty, score, pseudo, on_done=None):
    """Submit a score online in a background thread (offline-first).

    If the submission fails, the score is queued for the next sync attempt.
    on_done(success: bool) is called from the background thread when finished.
    """
    _add_pending(cert, difficulty, score, pseudo)  # queue immediately

    def _run():
        cfg = load_config()
        if not cfg:
            if on_done:
                on_done(False)
            return
        pending = _load_pending()
        synced = []
        for entry in pending:
            try:
                _post_score(cfg, entry['cert'], entry['difficulty'],
                            entry['score'], entry['pseudo'])
                synced.append(entry)
            except (URLError, OSError):
                break  # stop on first failure (keep remaining pending)
        if synced:
            remaining = [e for e in pending if e not in synced]
            _save_pending(remaining)
        success = len(synced) == len(pending)
        if on_done:
            on_done(success)

    threading.Thread(target=_run, daemon=True).start()


def fetch_online_scores_async(cert, difficulty, callback):
    """Fetch online scores in a background thread, call callback(list) when done."""
    def _run():
        results = fetch_online_scores(cert, difficulty)
        callback(results)
    threading.Thread(target=_run, daemon=True).start()
