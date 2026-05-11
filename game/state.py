"""Game state management and save/load."""

import json
import os
import sys
import time

from game.config import (
    POINTS, CATEGORY_UNLOCK_COST_BASE, CATEGORY_UNLOCK_COST_MULT,
    POWERS, UPGRADES, TIMER_BASE, TIMER_MIN, TIMER_DECAY_PER_LEVEL,
    DIFF3_UNLOCK_SCORE,
)


def get_save_path():
    """Get save file path.

    Bundled (.exe / Mac app): saves in the user data directory so it persists
    regardless of where the binary is installed or run from.
      Windows → %APPDATA%/PTShortcuts/save.json
      macOS   → ~/Library/Application Support/PTShortcuts/save.json
    Dev (running main.py directly): saves in the project root.
    """
    if getattr(sys, '_MEIPASS', None):
        if sys.platform == 'darwin':
            base = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'PTShortcuts')
        else:
            base = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'PTShortcuts')
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, 'save.json')
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'save.json')


class GameState:
    """Holds all mutable game state for a single certification session."""

    def __init__(self, certification_name, category_names):
        self.certification = certification_name
        self.all_categories = list(category_names)
        self.score = 0
        self.total_score = 0  # lifetime score (for buying)
        self.spent_score = 0  # track what's been spent
        self.combo = 0
        self.max_combo = 0
        self.total_correct = 0
        self.total_wrong = 0
        self.level = 1
        self.unlocked_categories = [self.all_categories[0]] if self.all_categories else []
        # Design v4: powers are score-gated, not inventory-based. These legacy
        # dicts are retained for save-file backwards-compat but no longer drive
        # gameplay. `is_power_unlocked()` uses lifetime score.
        self.upgrade_counts = {k: 0 for k in POWERS}
        self.upgrade_costs = {k: v['use_cost'] for k, v in POWERS.items()}
        # Custom mode flag: when True, all powers are unlocked AND free.
        self.free_upgrades = False

        # Active effects
        self.freeze_until = 0.0
        self.double_until = 0.0

        # Current shortcut state
        self.current_shortcut = None
        self.timer_start = 0.0
        self.timer_duration = TIMER_BASE
        self.revealed = False
        self.skipped = False

        # Feedback state
        self.feedback_text = ""
        self.feedback_color = (255, 255, 255)
        self.feedback_until = 0.0
        self.score_popups = []  # [(text, x, y, birth_time, color)]
        self.particles = []

    @property
    def available_score(self):
        return self.total_score - self.spent_score

    def get_timer_duration(self):
        """Timer decreases with level."""
        dur = TIMER_BASE - (self.level - 1) * TIMER_DECAY_PER_LEVEL
        return max(dur, TIMER_MIN)

    def get_max_difficulty(self):
        """Difficulty 3 unlocks after threshold."""
        if self.total_score >= DIFF3_UNLOCK_SCORE:
            return 3
        return 2

    def get_combo_multiplier(self):
        return max(1, self.combo)

    def on_correct(self):
        """Handle correct answer."""
        diff = self.current_shortcut.get('difficulty', 1)
        base = POINTS.get(diff, 10)
        multiplier = self.get_combo_multiplier()
        if time.time() < self.double_until:
            multiplier *= 2
        points = base * multiplier
        self.score += points
        self.total_score += points
        self.combo += 1
        self.max_combo = max(self.max_combo, self.combo)
        self.total_correct += 1

        # Level up every 10 correct answers
        self.level = 1 + self.total_correct // 10

        return points

    def on_wrong(self):
        """Handle wrong answer."""
        self.combo = 0
        self.total_wrong += 1

    def on_timeout(self):
        """Handle timer expiry."""
        self.combo = 0
        self.total_wrong += 1

    # ── Score-gated powers (Design v4) ────────────────────────────────────
    def is_power_unlocked(self, power_id):
        """A power is permanently unlocked once lifetime score ≥ unlock_cost.

        In custom mode (`free_upgrades`), every power is unlocked from the start.
        """
        p = POWERS.get(power_id)
        if p is None:
            return False
        if self.free_upgrades:
            return True
        return self.total_score >= p['unlock_cost']

    def can_use_power(self, power_id):
        """Unlocked AND available score covers the use cost.

        In custom mode (`free_upgrades`), powers are always usable.
        """
        p = POWERS.get(power_id)
        if p is None:
            return False
        if self.free_upgrades:
            return True
        return self.is_power_unlocked(power_id) and self.available_score >= p['use_cost']

    def power_unlock_progress(self, power_id):
        """Ratio 0..1 toward unlocking this power (for the lock overlay bar)."""
        p = POWERS.get(power_id)
        if p is None or p['unlock_cost'] <= 0:
            return 1.0
        return min(1.0, self.total_score / p['unlock_cost'])

    def use_power(self, power_id):
        """Pay the use cost and apply the power effect. Returns True on success.

        Callers still handle the side effect (e.g. advancing shortcut on skip)
        via the returned flags (`self.skipped`, `self.revealed`) or the
        explicit effect applied here (`freeze_until`, `double_until`).
        """
        if not self.can_use_power(power_id):
            return False
        if not self.free_upgrades:
            self.spent_score += POWERS[power_id]['use_cost']
        if power_id == 'skip':
            self.skipped = True
        elif power_id == 'reveal':
            self.revealed = True
        elif power_id == 'freeze':
            self.freeze_until = time.time() + 5.0
        elif power_id == 'double':
            self.double_until = time.time() + 15.0
        return True

    # Legacy wrappers — kept so older callers keep compiling. They all route
    # through use_power() now; the old "inventory count" model is gone.
    def buy_upgrade(self, upgrade_id):
        """Legacy API. Maps 'buy' to 'use' under the score-gated model."""
        return self.use_power(upgrade_id)

    def use_skip(self):
        return self.use_power('skip')

    def use_reveal(self):
        return self.use_power('reveal')

    def use_freeze(self):
        return self.use_power('freeze')

    def use_double(self):
        return self.use_power('double')

    def next_category_unlock_cost(self):
        """Cost to unlock next category (design v4: round(150 * 1.5^i))."""
        unlocked = len(self.unlocked_categories)
        if unlocked >= len(self.all_categories):
            return None
        return int(round(CATEGORY_UNLOCK_COST_BASE * (CATEGORY_UNLOCK_COST_MULT ** (unlocked - 1))))

    def next_category_name(self):
        """Name of the next locked category, or None if all unlocked."""
        unlocked = len(self.unlocked_categories)
        if unlocked >= len(self.all_categories):
            return None
        return self.all_categories[unlocked]

    def next_category_unlock_progress(self):
        """Ratio 0..1 of available score toward the next unlock cost."""
        cost = self.next_category_unlock_cost()
        if cost is None or cost <= 0:
            return 1.0
        return min(1.0, self.available_score / cost)

    def unlock_next_category(self):
        """Try to unlock next category."""
        cost = self.next_category_unlock_cost()
        if cost is None:
            return False
        if self.available_score < cost:
            return False
        self.spent_score += cost
        next_idx = len(self.unlocked_categories)
        self.unlocked_categories.append(self.all_categories[next_idx])
        return True

    def is_frozen(self):
        return time.time() < self.freeze_until

    def is_double(self):
        return time.time() < self.double_until

    def to_dict(self):
        return {
            'score': self.total_score,
            'spent': self.spent_score,
            'max_combo': self.max_combo,
            'total_correct': self.total_correct,
            'total_wrong': self.total_wrong,
            'level': self.level,
            'unlocked_categories': self.unlocked_categories,
            'upgrade_counts': self.upgrade_counts,
            'upgrade_costs': self.upgrade_costs,
        }

    def load_from_dict(self, data):
        self.total_score = data.get('score', 0)
        self.spent_score = data.get('spent', 0)
        self.score = self.total_score - self.spent_score
        self.max_combo = data.get('max_combo', 0)
        self.total_correct = data.get('total_correct', 0)
        self.total_wrong = data.get('total_wrong', 0)
        self.level = data.get('level', 1)
        saved_cats = data.get('unlocked_categories', [])
        # Only keep categories that still exist in current JSON
        self.unlocked_categories = [c for c in saved_cats if c in self.all_categories]
        if not self.unlocked_categories and self.all_categories:
            self.unlocked_categories = [self.all_categories[0]]
        self.upgrade_counts = data.get('upgrade_counts', self.upgrade_counts)
        self.upgrade_costs = data.get('upgrade_costs', self.upgrade_costs)


def save_game(states_dict):
    """Save all certification states to save.json (atomic write via temp file)."""
    path = get_save_path()
    tmp_path = path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(states_dict, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except OSError:
        pass


def load_game():
    """Load saved game data."""
    path = get_save_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def load_pseudo():
    """Return the saved player pseudo, or '' if not set."""
    return load_game().get('_pseudo', '')


def load_achievements():
    """Return set of unlocked achievement IDs."""
    return set(load_game().get('_achievements', {}).keys())


def save_achievements(unlocked_set):
    """Persist achievement IDs into save.json (atomic write)."""
    path = get_save_path()
    tmp_path = path + '.tmp'
    try:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
        existing = data.get('_achievements', {})
        for aid in unlocked_set:
            if aid not in existing:
                existing[aid] = time.time()
        data['_achievements'] = existing
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except OSError:
        pass


def load_stats(cert_name):
    """Return per-shortcut stats dict for a certification.

    Returns a dict: {command_name: {views, correct, total_time}}
    """
    return load_game().get('_stats', {}).get(cert_name, {})


def save_pseudo(pseudo):
    """Persist the player pseudo into save.json (atomic write)."""
    save_setting('_pseudo', pseudo)


def load_setting(key, default=None):
    """Read a top-level setting from save.json."""
    return load_game().get(key, default)


def save_setting(key, value):
    """Persist a top-level setting into save.json (atomic write)."""
    path = get_save_path()
    tmp_path = path + '.tmp'
    try:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
        data[key] = value
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except OSError:
        pass


def reset_all_data():
    """Erase all local data (pseudo, scores, upgrades, stats) from save.json."""
    path = get_save_path()
    tmp_path = path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        os.replace(tmp_path, path)
    except OSError:
        pass
