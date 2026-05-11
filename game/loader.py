"""Load certification modules from JSON files."""

import json
import os
import re
import sys

_VALID_INPUT_TYPES = {'key_combo', 'modifier_click', 'single_key', 'key_sequence'}


def _validate_shortcut(sc, filename, cat_name):
    """Validate a shortcut dict. Returns an error message string, or None if valid."""
    name = sc.get('command_name', '<sans nom>')

    if not isinstance(sc.get('command_name'), str) or not sc['command_name'].strip():
        return f"[{filename}] catégorie '{cat_name}': champ 'command_name' manquant ou vide"

    # keys_win ou keys doit exister et être une liste non vide
    keys = sc.get('keys_win', sc.get('keys'))
    if keys is None:
        return f"[{filename}] '{name}': champ 'keys_win' manquant"
    if not isinstance(keys, list) or len(keys) == 0:
        return f"[{filename}] '{name}': 'keys_win' doit être une liste non vide"

    input_type = sc.get('input_type', 'key_combo')
    if input_type not in _VALID_INPUT_TYPES:
        return f"[{filename}] '{name}': input_type invalide '{input_type}' (attendu: {', '.join(sorted(_VALID_INPUT_TYPES))})"

    if input_type == 'key_sequence':
        if not all(isinstance(step, list) for step in keys):
            return f"[{filename}] '{name}': key_sequence requiert une liste de listes dans 'keys_win'"

    return None


def get_shortcuts_dir():
    """Get the shortcuts directory, works both in dev and PyInstaller bundle."""
    if getattr(sys, '_MEIPASS', None):
        return os.path.join(sys._MEIPASS, 'shortcuts')
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shortcuts')


# ---------------------------------------------------------------------------
# Key name normalization: JSON key names → internal keyboard handler names
# ---------------------------------------------------------------------------

_MODIFIERS = {'Ctrl', 'Shift', 'Alt', 'Win', 'Start'}

_KEY_MAP = {
    'Start': 'Win',
}


def _normalize_one_key(k):
    """Normalize a single JSON key name to a list of acceptable internal names.

    Returns a list because some keys represent alternatives (e.g. "Up/Down Arrow").
    """
    # Any digit (number row + numpad)
    if k == 'AnyDigit':
        return [str(i) for i in range(10)] + [f'Num{i}' for i in range(10)]

    # Direct mapping
    if k in _KEY_MAP:
        return [_KEY_MAP[k]]

    # Numpad range: "Numpad 0-5"
    m = re.match(r'^Numpad (\d)-(\d)$', k)
    if m:
        return [f'Num{i}' for i in range(int(m.group(1)), int(m.group(2)) + 1)]

    # Single numpad: "Numpad 7"
    m = re.match(r'^Numpad (\d)$', k)
    if m:
        return [f'Num{m.group(1)}']

    # Arrow alternatives: "Up/Down Arrow", "Left/Right Arrow"
    m = re.match(r'^(\w+)/(\w+) Arrow$', k)
    if m:
        return [m.group(1), m.group(2)]

    # Single arrow: "Up Arrow", "Down Arrow", etc.
    m = re.match(r'^(\w+) Arrow$', k)
    if m:
        return [m.group(1)]

    # Function key range: "F1-F4"
    m = re.match(r'^F(\d+)-F(\d+)$', k)
    if m:
        return [f'F{i}' for i in range(int(m.group(1)), int(m.group(2)) + 1)]

    # Bare number range: "1-9", "0-5"
    m = re.match(r'^(\d+)-(\d+)$', k)
    if m:
        return [str(i) for i in range(int(m.group(1)), int(m.group(2)) + 1)]

    # Click types (not keyboard keys)
    if k in ('Click', 'Right-Click', 'Double-Click'):
        return [k]

    # Either/or keys: ")/=" or "Num+/Num-" or "Up/Down Arrow"
    if '/' in k:
        parts = k.split('/')
        # Expand each part individually and flatten
        result = []
        for part in parts:
            part = part.strip()
            if part:
                result.append(part)
        if len(result) >= 2:
            return result

    # Single char → uppercase
    if len(k) == 1:
        return [k.upper()]

    # Everything else passes through (Enter, Tab, Space, etc.)
    return [k]


def _build_detect_info(keys_list, input_type):
    """Build detection data from a keys_win list.

    Returns dict with:
      _detect_modifiers: frozenset of normalized modifier names
      _detect_key_options: list of frozensets — any one is acceptable
      _detect_click: 'left', 'right', or None
      _detect_input_type: str
    """
    modifiers = set()
    key_alternatives = []  # list of lists of alternatives
    click_type = None

    for k in keys_list:
        norm = k
        if k in _KEY_MAP:
            norm = _KEY_MAP[k]
        if norm in _MODIFIERS:
            modifiers.add(norm)
            continue
        if k == 'Click':
            click_type = 'left'
            continue
        if k == 'Double-Click':
            click_type = 'double'
            continue
        if k == 'Right-Click':
            click_type = 'right'
            continue
        # Non-modifier, non-click key
        alternatives = _normalize_one_key(k)
        key_alternatives.append(alternatives)

    # Build all possible combos from the cartesian product of alternatives
    # plus the modifiers. Usually there's 0 or 1 non-modifier key group.
    if not key_alternatives:
        # Modifier-only shortcut (e.g. just "Ctrl") or modifier+click
        options = [frozenset(modifiers)]
    else:
        # Build combos: modifiers + one choice from each alternative group
        from itertools import product as iterproduct
        options = []
        for combo in iterproduct(*key_alternatives):
            normalized = set(modifiers)
            for alt in combo:
                # Uppercase single chars for matching
                normalized.add(alt.upper() if len(alt) == 1 else alt)
            options.append(frozenset(normalized))

    return {
        '_detect_modifiers': frozenset(modifiers),
        '_detect_key_options': options,
        '_detect_click': click_type,
        '_detect_input_type': input_type,
    }


def _build_sequence_detect_info(steps_list):
    """Build detection data for a key_sequence shortcut.

    steps_list: list of lists, e.g. [["Ctrl","Alt","1"], ["B"]]
    Each step is processed like a regular combo via _build_detect_info.

    Returns dict with:
      _detect_input_type: 'key_sequence'
      _detect_steps: list of dicts, each from _build_detect_info
    """
    steps = []
    for step_keys in steps_list:
        step_info = _build_detect_info(step_keys, 'key_combo')
        steps.append(step_info)
    return {
        '_detect_input_type': 'key_sequence',
        '_detect_steps': steps,
    }


def _normalize_shortcut(sc):
    """Add detection fields and ensure both keys_mac/keys_win exist."""
    # New format: keys_mac + keys_win
    if 'keys_win' in sc:
        keys_win = sc['keys_win']
        input_type = sc.get('input_type', 'key_combo')
    elif 'keys' in sc:
        # Old format: single 'keys' field → use for both mac and win
        keys_win = sc['keys']
        sc['keys_win'] = keys_win
        sc['keys_mac'] = keys_win
        input_type = sc.get('input_type', 'key_combo')
    else:
        keys_win = []
        input_type = 'key_combo'

    if 'keys_mac' not in sc:
        sc['keys_mac'] = sc.get('keys', keys_win)

    # Build detection info
    if input_type == 'key_sequence':
        # keys_win is an array of arrays: [["Ctrl","Alt","1"], ["B"]]
        detect = _build_sequence_detect_info(keys_win)
    else:
        detect = _build_detect_info(keys_win, input_type)
    sc.update(detect)

    # Build detection info for alternatives (multiple valid shortcuts)
    if 'alt' in sc and isinstance(sc['alt'], list):
        alt_detects = []
        for alt in sc['alt']:
            alt_keys = alt.get('keys_win', [])
            alt_type = alt.get('input_type', input_type)
            if not alt_keys:
                continue
            if 'keys_mac' not in alt:
                alt['keys_mac'] = alt_keys
            if alt_type == 'key_sequence':
                alt_det = _build_sequence_detect_info(alt_keys)
            else:
                alt_det = _build_detect_info(alt_keys, alt_type)
            alt_det['input_type'] = alt_type
            alt_detects.append(alt_det)
        sc['_detect_alt'] = alt_detects


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_certifications():
    """Scan shortcuts/ folder and load all certification JSON files.

    Returns dict: {cert_name: cert_data} for valid files.
    """
    shortcuts_dir = get_shortcuts_dir()
    certifications = {}

    if not os.path.isdir(shortcuts_dir):
        return certifications

    for filename in sorted(os.listdir(shortcuts_dir)):
        if not filename.endswith('.json'):
            continue
        filepath = os.path.join(shortcuts_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cert_name = data.get('certification', filename[:-5])
            if 'categories' not in data or not isinstance(data['categories'], list):
                continue
            all_shortcuts = []
            categories = []
            for cat in data['categories']:
                if not isinstance(cat, dict) or not isinstance(cat.get('name'), str):
                    print(f"[loader] {filename}: catégorie ignorée (pas de champ 'name')", file=sys.stderr)
                    continue
                cat_name = cat['name']
                categories.append(cat_name)
                for sc in cat.get('shortcuts', []):
                    error = _validate_shortcut(sc, filename, cat_name)
                    if error:
                        print(f"[loader] Raccourci ignoré — {error}", file=sys.stderr)
                        continue
                    sc['category'] = cat_name
                    _normalize_shortcut(sc)
                    all_shortcuts.append(sc)
            data['all_shortcuts'] = all_shortcuts
            data['category_names'] = categories
            certifications[cert_name] = data
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    return certifications


_NUMPAD_KEY_NAMES = (
    {f'Num{i}' for i in range(10)} | {'Num.', 'Num/', 'Num*', 'Num+', 'Num-'}
)


def _combo_has_numpad(combo):
    return any(k in _NUMPAD_KEY_NAMES for k in combo)


def _detect_needs_numpad(detect):
    """True iff this detection path can only be satisfied with numpad keys."""
    itype = detect.get('_detect_input_type', 'key_combo')
    if itype == 'key_sequence':
        for step in detect.get('_detect_steps', []):
            opts = step.get('_detect_key_options', [])
            if opts and all(_combo_has_numpad(o) for o in opts):
                return True
        return False
    opts = detect.get('_detect_key_options', [])
    if not opts:
        return False
    return all(_combo_has_numpad(o) for o in opts)


def shortcut_requires_numpad(sc):
    """True if the shortcut is unplayable without numpad keys.

    The main path AND every alt path must require numpad. If any path is
    numpad-free the shortcut stays playable (user uses the non-numpad variant).
    """
    if not _detect_needs_numpad(sc):
        return False
    for alt in sc.get('_detect_alt', []):
        if not _detect_needs_numpad(alt):
            return False
    return True


def get_shortcuts_for_categories(cert_data, unlocked_categories):
    """Get shortcuts only from unlocked categories."""
    return [s for s in cert_data['all_shortcuts'] if s['category'] in unlocked_categories]


def get_weighted_shortcuts(shortcuts, max_difficulty=3, stats=None):
    """Filter shortcuts by max difficulty, return (items, weights) for random.choices.

    stats: optional dict {command_name: {views, correct, ...}} for adaptive weighting.
    Shortcuts with low success rates get a higher weight; mastered ones get lower weight.
    """
    filtered = [s for s in shortcuts if s.get('difficulty', 1) <= max_difficulty]
    if not filtered:
        filtered = shortcuts

    weights = []
    for s in filtered:
        base = s.get('weight', 5)
        if stats is not None:
            entry = stats.get(s.get('command_name', ''), {})
            views = entry.get('views', 0)
            correct = entry.get('correct', 0)
            if views > 0:
                rate = correct / views
                factor = max(0.3, 2.0 - 1.7 * rate)
                base = base * factor
        weights.append(base)

    return filtered, weights
