"""Game state management and save/load."""

import json
import os
import sys
import time

from game.config import (
    POINTS, CATEGORY_UNLOCK_COST_BASE, CATEGORY_UNLOCK_COST_MULT,
    UPGRADES, TIMER_BASE, TIMER_MIN, TIMER_DECAY_PER_LEVEL, DIFF3_UNLOCK_SCORE,
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
        self.upgrade_counts = {k: 0 for k in UPGRADES}
        self.upgrade_costs = {k: v['base_cost'] for k, v in UPGRADES.items()}

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

    def buy_upgrade(self, upgrade_id):
        """Try to buy an upgrade. Returns True if successful."""
        if upgrade_id not in UPGRADES:
            return False
        cost = self.upgrade_costs[upgrade_id]
        if self.available_score < cost:
            return False
        self.spent_score += cost
        self.upgrade_counts[upgrade_id] += 1
        self.upgrade_costs[upgrade_id] = int(
            UPGRADES[upgrade_id]['base_cost']
            * (UPGRADES[upgrade_id]['cost_mult'] ** self.upgrade_counts[upgrade_id])
        )
        return True

    def use_skip(self):
        if self.upgrade_counts['skip'] > 0:
            self.upgrade_counts['skip'] -= 1
            self.skipped = True
            return True
        return False

    def use_reveal(self):
        if self.upgrade_counts['reveal'] > 0:
            self.upgrade_counts['reveal'] -= 1
            self.revealed = True
            return True
        return False

    def use_freeze(self):
        if self.upgrade_counts['freeze'] > 0:
            self.upgrade_counts['freeze'] -= 1
            self.freeze_until = time.time() + 5.0
            return True
        return False

    def use_double(self):
        if self.upgrade_counts['double'] > 0:
            self.upgrade_counts['double'] -= 1
            self.double_until = time.time() + 15.0
            return True
        return False

    def next_category_unlock_cost(self):
        """Cost to unlock next category."""
        unlocked = len(self.unlocked_categories)
        if unlocked >= len(self.all_categories):
            return None
        return int(CATEGORY_UNLOCK_COST_BASE * (CATEGORY_UNLOCK_COST_MULT ** (unlocked - 1)))

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
    path = get_save_path()
    tmp_path = path + '.tmp'
    try:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
        data['_pseudo'] = pseudo
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
