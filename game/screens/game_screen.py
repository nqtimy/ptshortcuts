"""GameScreen — main gameplay with keyboard detection, particles, and power-ups."""

import math
import random
import time

import pygame

from game.config import *
from game.screens._shared import (
    _lc, _lf,
    _DBLCLICK_THRESHOLD,
    _LABEL_SMALL, _LABEL_BIG, _KEYS_SMALL, _KEYS_BIG, _COLOR_BIG,
    _to_azerty_display, _to_azerty_display_seq,
)
from game.loader import (
    get_shortcuts_for_categories, get_weighted_shortcuts,
    shortcut_requires_numpad,
)
from game.particles import (
    ScorePopup, RingParticle, spawn_explosion, spawn_sparks,
    spawn_firework_ring, spawn_embers, spawn_wrong_burst, spawn_ripple,
)
from game.renderer import (
    draw_border_glow, draw_button, draw_combo_text, draw_flash, draw_glow_rect,
    draw_key_combo, draw_key_sequence, draw_particles, draw_ripples,
    draw_rounded_rect,
    draw_score_popups, draw_shadow_rect, draw_text, draw_text_glow,
    draw_timer_bar, draw_vignette, get_font,
    draw_text_gradient, draw_gradient_rect, draw_radial_halo, draw_padlock,
    draw_progress_bar, draw_corner_frame,
    ease_out_cubic, lerp_color, lerp_color_stops, frame_lerp,
    _get_glow_surface, _scale_alpha,
)
from game.achievements import ACHIEVEMENTS
from game.leaderboard import save_local_highscore, submit_score_async
from game.state import (GameState, load_game, save_game, load_pseudo,
                        load_stats, load_achievements, save_achievements)


# ---------------------------------------------------------------------------
# Visual keyboard layout (QWERTY Mac labels + internal key names)
# Each key: (display_label, internal_name_or_None, width_in_units)
# Total width per row ≈ 15 units.
# ---------------------------------------------------------------------------

_KB_ROWS = [
    # Number row
    [('`', '`', 1.0), ('1', '1', 1.0), ('2', '2', 1.0), ('3', '3', 1.0),
     ('4', '4', 1.0), ('5', '5', 1.0), ('6', '6', 1.0), ('7', '7', 1.0),
     ('8', '8', 1.0), ('9', '9', 1.0), ('0', '0', 1.0), ('-', '-', 1.0),
     ('=', '=', 1.0), ('Del', None, 2.0)],
    # Top letter row
    [('Tab', None, 1.5), ('Q', 'Q', 1.0), ('W', 'W', 1.0), ('E', 'E', 1.0),
     ('R', 'R', 1.0), ('T', 'T', 1.0), ('Y', 'Y', 1.0), ('U', 'U', 1.0),
     ('I', 'I', 1.0), ('O', 'O', 1.0), ('P', 'P', 1.0), ('[', '[', 1.0),
     (']', ']', 1.0), ('\\', '\\', 1.5)],
    # Home row
    [('Caps', None, 1.75), ('A', 'A', 1.0), ('S', 'S', 1.0), ('D', 'D', 1.0),
     ('F', 'F', 1.0), ('G', 'G', 1.0), ('H', 'H', 1.0), ('J', 'J', 1.0),
     ('K', 'K', 1.0), ('L', 'L', 1.0), (';', ';', 1.0), ("'", "'", 1.0),
     ('Ret', 'Enter', 2.25)],
    # Bottom row
    [('Shift', 'Shift', 2.25), ('Z', 'Z', 1.0), ('X', 'X', 1.0), ('C', 'C', 1.0),
     ('V', 'V', 1.0), ('B', 'B', 1.0), ('N', 'N', 1.0), ('M', 'M', 1.0),
     (',', ',', 1.0), ('.', '.', 1.0), ('/', '/', 1.0), ('Shift', 'Shift', 2.75)],
    # Modifier row (Mac labels: Ctrl=Control, Opt=Option, Cmd=Command)
    [('Ctrl', 'Win', 1.5), ('Opt', 'Alt', 1.25), ('Cmd', 'Ctrl', 1.5),
     ('Space', 'Space', 6.5), ('Cmd', 'Ctrl', 1.5), ('Opt', 'Alt', 1.25),
     ('Ctrl', 'Win', 1.5)],
]
_KB_TOTAL_UNITS = 15.0  # approx row width in units

# Numpad layout (Design v4). Each entry: (label, internal_name, col, row,
# col_span, row_span). 4 columns × 5 rows grid.
_NUMPAD_KEYS = [
    ('/',     'Num/',     0, 0, 1, 1),
    ('*',     'Num*',     1, 0, 1, 1),
    ('-',     'Num-',     2, 0, 1, 1),
    ('7',     'Num7',     0, 1, 1, 1),
    ('8',     'Num8',     1, 1, 1, 1),
    ('9',     'Num9',     2, 1, 1, 1),
    ('+',     'Num+',     3, 1, 1, 2),
    ('4',     'Num4',     0, 2, 1, 1),
    ('5',     'Num5',     1, 2, 1, 1),
    ('6',     'Num6',     2, 2, 1, 1),
    ('1',     'Num1',     0, 3, 1, 1),
    ('2',     'Num2',     1, 3, 1, 1),
    ('3',     'Num3',     2, 3, 1, 1),
    ('Ent',   'NumEnter', 3, 3, 1, 2),
    ('0',     'Num0',     0, 4, 2, 1),
    ('.',     'Num.',     2, 4, 1, 1),
]


# ---------------------------------------------------------------------------
# Game Screen
# ---------------------------------------------------------------------------

class GameScreen:
    """Main gameplay screen with explosive effects."""

    def __init__(self, cert_name, cert_data, kbd_handler, max_difficulty=3,
                 custom_mode=False, timer_enabled=True,
                 custom_bonus=False, custom_show_answer=False, custom_random=True,
                 no_numpad=False):
        self.cert_name = cert_name
        self.cert_data = cert_data
        self.kbd = kbd_handler
        self.max_difficulty = max_difficulty
        # custom_mode replaces the former "review_mode": tweakable revision sandbox.
        self.custom_mode = custom_mode
        self.timer_enabled = timer_enabled
        self.custom_bonus = custom_bonus
        self.custom_show_answer = custom_show_answer
        self.custom_random = custom_random
        self.no_numpad = no_numpad
        # Whether the upgrades/bonus panel + action buttons are visible.
        # Classic mode: always shown. Custom mode: only when bonus is enabled.
        self._show_bonus_panel = (not custom_mode) or custom_bonus

        # Init state
        self.state = GameState(cert_name, cert_data['category_names'])
        saved = load_game()
        # Load persisted state only for classic mode (custom mode doesn't persist).
        if not custom_mode and cert_name in saved:
            self.state.load_from_dict(saved[cert_name])
        self.state.total_score = 0
        self.state.spent_score = 0
        if custom_mode and custom_bonus:
            # Custom + bonus: powers are unlocked + free.
            self.state.free_upgrades = True
            self.state.unlocked_categories = list(self.state.all_categories)

        # Particles and effects
        self.particles = []
        self.popups = []
        # Background ripples — drawn behind UI cards. Separate list because of
        # z-order (rendered early in draw, before the cards).
        self.ripples = []
        self.flash_color = None
        self.flash_until = 0.0
        # Anchor for popups/particles — set every draw from the answer card rect.
        self._answer_card_rect = None

        # Screen shake
        self.shake_intensity = 0.0
        self.shake_x = 0
        self.shake_y = 0

        # Rects
        self.upgrade_rects = {}       # legacy name, now holds PowerCard rects
        self.cat_unlock_rect = None   # "Leçon suivante" button
        self.back_rect = None
        self.hovered_upgrade = None
        self.action_rects = {}        # kept for legacy click routing (unused in v4)
        self._power_hover_t = {k: 0.0 for k in POWERS}

        # ── Design v4: animation state ────────────────────────────────────
        # Animated score counter (eases toward available_score over 600ms)
        self._display_score = 0.0
        self._score_anim_from = 0.0
        self._score_anim_to = 0.0
        self._score_anim_start = 0.0
        self._last_score_target = 0  # detect changes → restart anim
        # Flash on correct (0..1 decays after correct answer)
        self._score_flash_t = 0.0
        self._combo_bump_t = 0.0      # popIn animation on combo change
        self._prev_combo_bump = 0
        # Keycap reveal fade-in (0..1 lerps to 1 when revealed)
        self._reveal_fade_t = 0.0
        # Unlock-lesson button "DISPONIBLE!" pulse
        self._lesson_available_t = 0.0
        self._lesson_was_available = False

        # Game over
        self.game_over = False
        self.game_over_time = 0.0
        self.game_over_restart_rect = None
        self.game_over_menu_rect = None
        self.game_over_answer = None
        self._go_restart_hover_t = 0.0
        self._go_menu_hover_t = 0.0
        self._go_last_draw = 0.0

        # Previous combo (to detect milestones)
        self._prev_combo = 0

        # Per-shortcut stats (in-memory cache, flushed on _save())
        self._stats_cache = load_stats(cert_name)
        self._shortcut_shown_at = 0.0  # time.time() when current shortcut was displayed

        # Achievements
        self._achievements_unlocked = load_achievements()
        self._achievement_queue = []   # list of {'id', 'born'} dicts
        self._consecutive_correct = 0  # streak counter for no_wrong_10
        self._total_correct_ever = sum(
            e.get('correct', 0) for e in self._stats_cache.values()
        )  # cumulative correct count before this session

        # Key sequence tracking (for key_sequence input_type)
        self._seq_step = 0  # current step index in the sequence

        # Double-click tracking (for modifier_click with _detect_click == 'double')
        self._dblclick_time = 0.0  # time.time() of first click
        self._dblclick_mods_ok = False  # whether first click had correct mods

        # Review mode: sequential playlist of all shortcuts
        self._custom_playlist = []
        self._custom_index = 0
        if self.custom_mode:
            self._build_custom_playlist()

        self._next_shortcut()

    def _build_custom_playlist(self):
        """Build a list of all shortcuts at the selected difficulty.

        custom_random ON  → shuffle
        custom_random OFF → sort by difficulty ascending
        """
        all_sc = self.cert_data.get('all_shortcuts', [])
        playlist = [s for s in all_sc if s.get('difficulty', 1) <= self.max_difficulty]
        if self.no_numpad:
            playlist = [s for s in playlist if not shortcut_requires_numpad(s)]
        if self.custom_random:
            random.shuffle(playlist)
        else:
            playlist.sort(key=lambda s: s.get('difficulty', 1))
        self._custom_playlist = playlist
        self._custom_index = 0

    def _next_shortcut(self):
        if self.custom_mode:
            if not self._custom_playlist:
                return
            # Loop: reshuffle / re-sort when we've gone through all
            if self._custom_index >= len(self._custom_playlist):
                if self.custom_random:
                    random.shuffle(self._custom_playlist)
                self._custom_index = 0
            chosen = self._custom_playlist[self._custom_index]
            self._custom_index += 1
            self.state.current_shortcut = chosen
            self.state.timer_duration = self.state.get_timer_duration()
            self.state.timer_start = time.time()
            self.state.revealed = False
            self.state.skipped = False
            self._seq_step = 0
            self._dblclick_time = 0.0
            self.kbd.clear()
            self._record_view(chosen)
            return

        shortcuts = get_shortcuts_for_categories(self.cert_data, self.state.unlocked_categories)
        if self.no_numpad:
            shortcuts = [s for s in shortcuts if not shortcut_requires_numpad(s)]
        if not shortcuts:
            return
        filtered, weights = get_weighted_shortcuts(shortcuts, self.max_difficulty,
                                                   stats=self._stats_cache)
        chosen = random.choices(filtered, weights=weights, k=1)[0]
        self.state.current_shortcut = chosen
        self.state.timer_duration = self.state.get_timer_duration()
        self.state.timer_start = time.time()
        self.state.revealed = False
        self.state.skipped = False
        self._seq_step = 0
        self._dblclick_time = 0.0
        self.kbd.clear()
        self._record_view(chosen)

    def _collect_combo_options(self, sc):
        """Return a combined list of _detect_key_options for the main shortcut
        plus all non-modifier-only alt variants. Used in a single
        check_combo_v2 call so we don't consume the combo during the main
        check and miss alts on the follow-up.
        """
        opts = list(sc.get('_detect_key_options', []))
        for alt_det in sc.get('_detect_alt', []):
            alt_type = alt_det.get('_detect_input_type', 'key_combo')
            alt_opts = alt_det.get('_detect_key_options', [])
            if not alt_opts:
                continue
            if alt_type in ('key_combo', 'single_key'):
                first_opt = next(iter(alt_opts[0])) if alt_opts else ''
                # Skip pure-modifier alts — they use check_modifier_only
                if first_opt not in ('Win', 'Ctrl', 'Shift', 'Alt'):
                    opts.extend(alt_opts)
        return opts

    def _check_alt_modifier_only(self, sc):
        """Check modifier-only alts (rare — e.g. Shift as an alt of Ctrl)."""
        for alt_det in sc.get('_detect_alt', []):
            if alt_det.get('_detect_input_type') != 'single_key':
                continue
            alt_opts = alt_det.get('_detect_key_options', [])
            if not alt_opts:
                continue
            first_opt = next(iter(alt_opts[0]))
            if first_opt in ('Win', 'Ctrl', 'Shift', 'Alt'):
                if self.kbd.check_modifier_only(
                        alt_det.get('_detect_modifiers')) is True:
                    self._do_correct()
                    return True
        return False

    def _check_alt_combo(self, sc):
        """Legacy alias kept for callers that only care about modifier-only
        alts post-consumption. Non-modifier alts should be folded into the
        main check_combo_v2 call via _collect_combo_options.
        """
        return self._check_alt_modifier_only(sc)

    def _get_live_preview_keys(self):
        """Return an ordered list of currently-pressed keys for live preview.

        Modifiers come first in canonical order, then non-modifier keys
        sorted for stability. Returns [] when nothing is held — caller falls
        back to `?` placeholders. Uses the locked `get_current_keys()` so
        we don't race the keyboard listener thread.
        """
        held = self.kbd.get_current_keys()
        ordered = [m for m in MODIFIER_ORDER if m in held]
        ordered.extend(sorted(k for k in held if k not in MODIFIER_ORDER))
        return ordered

    def _effect_anchor(self, click_pos=None, jitter=True):
        """Return (x, y) where popups/particles should spawn for the active shortcut.

        - If a click position is given (modifier_click feedback), use it directly.
        - Otherwise, anchor on the "APPUYEZ SUR" card with optional random jitter
          so successive popups don't stack on top of each other.
        """
        if click_pos is not None:
            return (int(click_pos[0]), int(click_pos[1]))
        r = self._answer_card_rect
        if r is not None:
            cx, cy = r.centerx, r.centery
            if jitter:
                jx = random.randint(-int(r.w * 0.28), int(r.w * 0.28))
                jy = random.randint(-int(r.h * 0.22), int(r.h * 0.22))
                return (cx + jx, cy + jy)
            return (cx, cy)
        w = pygame.display.get_surface().get_size()[0]
        return ((w - 260) // 2, 300)

    def _do_correct(self, at=None):
        response_time = max(0.0, time.time() - self._shortcut_shown_at)
        self._record_correct(self.state.current_shortcut)
        points = self.state.on_correct()
        self._score_flash_t = 1.0  # design v4: scoreUp animation
        self._check_achievements_correct(response_time)

        ax, ay = self._effect_anchor(at, jitter=True)

        # Score popup
        big = self.state.combo >= 5
        self.popups.append(ScorePopup(
            f"+{points}", ax, ay - 40,
            ACCENT_GREEN if self.state.combo < 5 else ACCENT_GOLD,
            big=big
        ))

        # Particles — explosive!
        combo = self.state.combo
        if combo >= 10:
            color = ACCENT_GOLD
            self.particles.extend(spawn_explosion(ax, ay, color, PARTICLES_CORRECT_HIGH))
            self.particles.extend(spawn_sparks(ax, ay, (255, 255, 200), 30))
        elif combo >= 5:
            color = ACCENT_GOLD
            self.particles.extend(spawn_explosion(ax, ay, color, PARTICLES_CORRECT))
            self.particles.extend(spawn_sparks(ax, ay, color, 15))
        else:
            color = ACCENT_GREEN
            self.particles.extend(spawn_explosion(ax, ay, color, PARTICLES_CORRECT))

        # Background ripple — one wave per event. Intensity scales with combo:
        # at 25+ the ripple spans the screen.
        if combo >= 25:
            ripple_intensity = 4.0
        elif combo >= 15:
            ripple_intensity = 2.8
        elif combo >= 10:
            ripple_intensity = 2.0
        elif combo >= 5:
            ripple_intensity = 1.4
        else:
            ripple_intensity = 0.9
        self.ripples.append(spawn_ripple(ax, ay, color, ripple_intensity))

        # Combo milestone fireworks
        if combo in COMBO_MILESTONES and combo > self._prev_combo:
            self.particles.extend(spawn_firework_ring(ax, ay, ACCENT_GOLD,
                                                      PARTICLES_MILESTONE))
            self.popups.append(ScorePopup(
                f"COMBO x{combo}!", ax, ay - 80, ACCENT_PURPLE, big=True
            ))
            self.shake_intensity = max(self.shake_intensity, SHAKE_GAME_OVER)

        self._prev_combo = combo

        # Screen shake
        self.shake_intensity = max(self.shake_intensity, SHAKE_CORRECT + min(combo, 10))

        # Flash
        self.flash_color = ACCENT_GREEN
        self.flash_until = time.time() + 0.12

        self._save()
        self._next_shortcut()

    def _do_wrong(self, at=None):
        self.state.on_wrong()
        self._prev_combo = 0
        self._consecutive_correct = 0
        self.flash_color = ACCENT_RED
        self.flash_until = time.time() + 0.25
        self.shake_intensity = max(self.shake_intensity, SHAKE_WRONG)

        ax, ay = self._effect_anchor(at, jitter=True)
        self.popups.append(ScorePopup("RATÉ", ax, ay, ACCENT_RED))
        self.particles.extend(spawn_wrong_burst(ax, ay + 20, PARTICLES_WRONG))
        self._save()

    def _do_timeout(self):
        self.state.on_timeout()
        self._prev_combo = 0
        self._consecutive_correct = 0
        self.game_over = True
        self.game_over_time = time.time()
        self.game_over_answer = self.state.current_shortcut
        self.flash_color = ACCENT_RED
        self.flash_until = time.time() + 0.6
        self.shake_intensity = SHAKE_GAME_OVER
        self._save()

    def _restart(self):
        self.state.total_score = 0
        self.state.spent_score = 0
        self.state.combo = 0
        self.state.max_combo = 0
        self.state.total_correct = 0
        self.state.total_wrong = 0
        self.state.level = 1
        self._prev_combo = 0
        self.game_over = False
        self.game_over_answer = None
        self.shake_intensity = 0
        self.particles.clear()
        self.popups.clear()
        self.ripples.clear()
        self._next_shortcut()

    def _unlock_achievement(self, aid):
        """Unlock an achievement if not already unlocked, and queue a notification."""
        # Custom mode is a sandbox: no achievement unlocks.
        if self.custom_mode:
            return
        if aid in self._achievements_unlocked:
            return
        self._achievements_unlocked.add(aid)
        save_achievements(self._achievements_unlocked)
        self._achievement_queue.append({'id': aid, 'born': time.time()})

    def _check_achievements_correct(self, response_time):
        """Check and unlock achievements after a correct answer."""
        combo = self.state.combo
        self._consecutive_correct += 1
        self._total_correct_ever += 1
        total = self._total_correct_ever

        # Combo milestones (check AFTER on_correct increments combo)
        if combo >= 50: self._unlock_achievement('combo_50')
        elif combo >= 25: self._unlock_achievement('combo_25')
        elif combo >= 10: self._unlock_achievement('combo_10')
        elif combo >= 5:  self._unlock_achievement('combo_5')

        # Correct count milestones
        if total >= 500:  self._unlock_achievement('correct_500')
        elif total >= 100: self._unlock_achievement('correct_100')
        elif total >= 10:  self._unlock_achievement('correct_10')
        elif total >= 1:   self._unlock_achievement('correct_1')

        # Speed achievements
        if response_time < 1.0: self._unlock_achievement('speed_1')
        elif response_time < 2.0: self._unlock_achievement('speed_2')

        # Streak
        if self._consecutive_correct >= 10:
            self._unlock_achievement('no_wrong_10')

    def _record_view(self, shortcut):
        """Increment the view count for a shortcut and record display time."""
        key = shortcut.get('command_name', '')
        if not key:
            return
        entry = self._stats_cache.setdefault(key, {'views': 0, 'correct': 0, 'total_time': 0.0})
        entry['views'] += 1
        self._shortcut_shown_at = time.time()

    def _record_correct(self, shortcut):
        """Record a correct answer with response time."""
        key = shortcut.get('command_name', '')
        if not key:
            return
        entry = self._stats_cache.setdefault(key, {'views': 0, 'correct': 0, 'total_time': 0.0})
        entry['correct'] += 1
        entry['total_time'] += max(0.0, time.time() - self._shortcut_shown_at)

    def _save(self):
        # Custom mode is a sandbox: no score, no stats, no leaderboard.
        if self.custom_mode:
            return
        saved = load_game()
        saved[self.cert_name] = self.state.to_dict()
        if '_stats' not in saved:
            saved['_stats'] = {}
        saved['_stats'][self.cert_name] = self._stats_cache
        save_game(saved)

        if self.state.total_score > 0:
            pseudo = load_pseudo() or 'Anonyme'
            is_new_record = save_local_highscore(
                self.cert_name, self.max_difficulty,
                self.state.total_score, pseudo
            )
            if is_new_record:
                submit_score_async(self.cert_name, self.max_difficulty,
                                   self.state.total_score, pseudo)

    def _is_ui_click(self, pos):
        """Check if pos hits any UI button."""
        if self.back_rect and self.back_rect.collidepoint(pos):
            return True
        if self.game_over:
            if self.game_over_restart_rect and self.game_over_restart_rect.collidepoint(pos):
                return True
            if self.game_over_menu_rect and self.game_over_menu_rect.collidepoint(pos):
                return True
        for rect in self.upgrade_rects.values():
            if rect.collidepoint(pos):
                return True
        if self.cat_unlock_rect and self.cat_unlock_rect.collidepoint(pos):
            return True
        for rect in self.action_rects.values():
            if rect.collidepoint(pos):
                return True
        return False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            is_left = event.button == 1
            is_right = event.button == 3

            # --- modifier_click detection (only if not clicking a UI element) ---
            if (is_left or is_right) and not self.game_over and not self._is_ui_click(pos):
                sc = self.state.current_shortcut
                if sc and sc.get('_detect_input_type') == 'modifier_click':
                    expected_click = sc.get('_detect_click', 'left')

                    # --- Helper: does this click event satisfy the expected type? ---
                    def _click_type_ok(exp, is_l, is_r):
                        if exp == 'left':
                            return is_l
                        if exp == 'right':
                            return is_r
                        if exp == 'double':
                            return is_l  # double-click uses left button
                        return False

                    # --- Helper: check double-click state machine ---
                    def _try_double(mods_expected):
                        """For 'double' click type: first click records, second validates.
                        Returns: 'correct' | 'wait' | 'wrong'."""
                        now = time.time()
                        if not self.kbd.check_modifiers_for_click(mods_expected):
                            self._dblclick_time = 0.0
                            return 'wrong'
                        if now - self._dblclick_time < _DBLCLICK_THRESHOLD:
                            self._dblclick_time = 0.0
                            return 'correct'
                        # First click — record and wait for second
                        self._dblclick_time = now
                        return 'wait'

                    # --- Primary shortcut check ---
                    if _click_type_ok(expected_click, is_left, is_right):
                        exp_mods = sc.get('_detect_modifiers', frozenset())
                        if expected_click == 'double':
                            result = _try_double(exp_mods)
                            if result == 'correct':
                                self._do_correct(at=pos)
                                return None
                            elif result == 'wait':
                                return None  # waiting for second click
                            # 'wrong' falls through to alt check
                        else:
                            if self.kbd.check_modifiers_for_click(exp_mods):
                                self._do_correct(at=pos)
                                return None

                    # --- Alt shortcut check ---
                    alt_matched = False
                    for alt_det in sc.get('_detect_alt', []):
                        if alt_det.get('_detect_input_type') != 'modifier_click':
                            continue
                        alt_click = alt_det.get('_detect_click', 'left')
                        if not _click_type_ok(alt_click, is_left, is_right):
                            continue
                        alt_mods = alt_det.get('_detect_modifiers', frozenset())
                        if alt_click == 'double':
                            result = _try_double(alt_mods)
                            if result == 'correct':
                                self._do_correct(at=pos)
                                alt_matched = True
                                break
                            elif result == 'wait':
                                alt_matched = True  # don't judge yet
                                break
                        else:
                            if self.kbd.check_modifiers_for_click(alt_mods):
                                self._do_correct(at=pos)
                                alt_matched = True
                                break
                    if alt_matched:
                        return None
                    self._do_wrong(at=pos)
                    return None

            if is_left:
                if self.game_over:
                    if self.game_over_restart_rect and self.game_over_restart_rect.collidepoint(pos):
                        self._restart()
                        return None
                    if self.game_over_menu_rect and self.game_over_menu_rect.collidepoint(pos):
                        self._save()
                        return 'menu'
                    return None

                if self.back_rect and self.back_rect.collidepoint(pos):
                    self._save()
                    return 'menu'

                if self._show_bonus_panel:
                    # Score-gated power cards
                    for uid, rect in self.upgrade_rects.items():
                        if rect.collidepoint(pos):
                            if self.state.use_power(uid):
                                self._unlock_achievement('upgrade_1')
                                if uid == 'skip':
                                    self._next_shortcut()
                                elif uid == 'reveal':
                                    self._unlock_achievement('reveal_1')
                            return None

                    # Unlock next lesson (disabled in custom mode anyway).
                    if (not self.custom_mode and self.cat_unlock_rect
                            and self.cat_unlock_rect.collidepoint(pos)):
                        if self.state.unlock_next_category():
                            self._unlock_achievement('cat_unlock')
                        return None
        return None

    def update(self, dt):
        now = time.time()

        if not self.game_over:
            if self.state.current_shortcut:
                sc = self.state.current_shortcut
                input_type = sc.get('_detect_input_type', 'key_combo')
                detect_opts = sc.get('_detect_key_options', [])

                if input_type == 'key_sequence':
                    # Multi-step sequence: validate one step at a time
                    steps = sc.get('_detect_steps', [])
                    absorb = set(sc.get('absorb_steps', []))
                    if steps and self._seq_step < len(steps):
                        actual = self.kbd.peek_last_combo()
                        if actual is not None:
                            cur_idx = self._seq_step
                            cur_opts = steps[cur_idx].get('_detect_key_options', [])

                            if cur_idx in absorb and cur_idx + 1 < len(steps):
                                # Absorb step: check END marker first, then digit
                                next_opts = steps[cur_idx + 1].get('_detect_key_options', [])
                                if actual in next_opts:
                                    self.kbd.consume_last_combo()
                                    self._seq_step = cur_idx + 2
                                    self.kbd.clear()
                                    if self._seq_step >= len(steps):
                                        self._do_correct()
                                elif actual in cur_opts:
                                    # Digit accepted, stay on absorb step
                                    self.kbd.consume_last_combo()
                                    self.kbd.clear()
                                else:
                                    self.kbd.consume_last_combo()
                                    self._seq_step = 0
                                    self._do_wrong()
                            else:
                                # Normal step
                                if actual in cur_opts:
                                    self.kbd.consume_last_combo()
                                    self._seq_step += 1
                                    self.kbd.clear()
                                    if self._seq_step >= len(steps):
                                        self._do_correct()
                                else:
                                    self.kbd.consume_last_combo()
                                    self._seq_step = 0
                                    self._do_wrong()
                elif input_type == 'modifier_click':
                    # modifier_click is handled in handle_event via mouse click
                    pass
                elif input_type == 'single_key' and detect_opts:
                    first_opt = next(iter(detect_opts[0])) if detect_opts else ''
                    if first_opt in ('Win', 'Ctrl', 'Shift', 'Alt'):
                        # Modifier-only shortcut: check if held alone
                        result = self.kbd.check_modifier_only(sc.get('_detect_modifiers'))
                        if result is True:
                            self._do_correct()
                    else:
                        # Include alts in the same check so we don't consume
                        # the combo on the main check and lose it.
                        all_opts = self._collect_combo_options(sc)
                        result = self.kbd.check_combo_v2(all_opts)
                        if result is True:
                            self._do_correct()
                        elif result is False:
                            if not self._check_alt_modifier_only(sc):
                                self._do_wrong()
                else:
                    all_opts = self._collect_combo_options(sc)
                    result = self.kbd.check_combo_v2(all_opts)
                    if result is True:
                        self._do_correct()
                    elif result is False:
                        if not self._check_alt_modifier_only(sc):
                            self._do_wrong()

            if self.state.current_shortcut:
                if self.state.is_frozen():
                    self.state.timer_start += dt
                elif not self.timer_enabled:
                    self.state.timer_start = now  # timer never expires
                elif self.custom_mode:
                    # Review mode: no game over, just skip on timeout
                    elapsed = now - self.state.timer_start
                    if elapsed >= self.state.timer_duration:
                        self._next_shortcut()
                else:
                    elapsed = now - self.state.timer_start
                    if elapsed >= self.state.timer_duration:
                        self._do_timeout()

            # Ambient embers during high combo
            if self.state.combo >= 5 and len(self.particles) < MAX_PARTICLES:
                w = pygame.display.get_surface().get_size()[0]
                game_w = w - 260
                ember_count = min(PARTICLES_EMBER_RATE,
                                  1 + self.state.combo // 5)
                self.particles.extend(spawn_embers(game_w // 2, 500, game_w, ember_count))
        else:
            self.kbd.get_last_combo()

        # Update particles
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.alive(now)]
        # Cap particle count
        if len(self.particles) > MAX_PARTICLES:
            self.particles = self.particles[-MAX_PARTICLES:]

        # Update popups
        for p in self.popups:
            p.update(dt)
        self.popups = [p for p in self.popups if p.alive(now)]

        # Cull dead ripples and FIFO-cap (mash-spam protection).
        if self.ripples:
            self.ripples = [r for r in self.ripples if r.alive(now)][-MAX_RIPPLES:]

        # Screen shake decay
        if self.shake_intensity > 0.5:
            self.shake_x = int(random.uniform(-self.shake_intensity, self.shake_intensity))
            self.shake_y = int(random.uniform(-self.shake_intensity, self.shake_intensity))
            self.shake_intensity *= SHAKE_DECAY
        else:
            self.shake_intensity = 0
            self.shake_x = 0
            self.shake_y = 0

        # Hover
        mouse = pygame.mouse.get_pos()
        self.hovered_upgrade = None
        for uid, rect in self.upgrade_rects.items():
            if rect.collidepoint(mouse):
                self.hovered_upgrade = uid

        # ── Design v4 animations ──────────────────────────────────────────
        # Animated score counter (ease-out cubic over 600ms toward available_score)
        target = self.state.available_score
        if target != self._last_score_target:
            self._score_anim_from = self._display_score
            self._score_anim_to = float(target)
            self._score_anim_start = now
            self._last_score_target = target
        if self._score_anim_to != self._score_anim_from:
            t = min(1.0, (now - self._score_anim_start) / SCORE_ANIM_DURATION)
            self._display_score = (self._score_anim_from
                + (self._score_anim_to - self._score_anim_from) * ease_out_cubic(t))
            if t >= 1.0:
                self._score_anim_from = self._score_anim_to
                self._display_score = self._score_anim_to
        # Flash decay
        self._score_flash_t = max(0.0, self._score_flash_t - dt * 2.5)
        # Combo pop-in on value change
        if self.state.combo != self._prev_combo_bump:
            self._combo_bump_t = 1.0
            self._prev_combo_bump = self.state.combo
        self._combo_bump_t = max(0.0, self._combo_bump_t - dt * 3.0)
        # Reveal fade
        rev_target = 1.0 if (self.state.revealed or self.custom_show_answer) else 0.0
        self._reveal_fade_t += (rev_target - self._reveal_fade_t) * frame_lerp(0.18, dt)
        # "Leçon suivante" availability pulse
        lesson_cost = self.state.next_category_unlock_cost()
        lesson_avail = lesson_cost is not None and self.state.available_score >= lesson_cost
        if lesson_avail and not self._lesson_was_available:
            self._lesson_available_t = 1.0
        self._lesson_available_t = max(0.0, self._lesson_available_t - dt * 2.0)
        self._lesson_was_available = lesson_avail
        # Hover decay for power cards
        for uid in POWERS:
            rect = self.upgrade_rects.get(uid)
            tgt = 1.0 if (rect is not None and rect.collidepoint(mouse)) else 0.0
            self._power_hover_t[uid] += (tgt - self._power_hover_t[uid]) * frame_lerp(0.18, dt)

    def get_shake_offset(self):
        return self.shake_x, self.shake_y

    def draw(self, surface):
        w, h = surface.get_size()
        surface.fill(BG_COLOR)
        now = time.time()

        # ── Design v4 layout constants (scaled for 1280×720) ──────────────
        TOP_BAR_H = 72
        LEFT_W = 330
        PAD = 20
        GAP = 14
        KB_H = 170  # bottom keyboard+numpad strip

        # Main area occupies full width (no right sidebar in v4)
        game_area_w = w
        game_cx = w // 2

        # Purple radial halo at top of screen (design v4 signature)
        draw_radial_halo(surface, w // 2, 0, int(w * 0.55), 240,
                         ACCENT_PURPLE, alpha=52, falloff=2.2)

        # Background ripples — behind every UI panel. One per correct/wrong event.
        if self.ripples:
            draw_ripples(surface, self.ripples)

        # ── TOP BAR ───────────────────────────────────────────────────────
        top_bar_rect = pygame.Rect(0, 0, w, TOP_BAR_H)
        pygame.draw.rect(surface, (*BG_CARD, 255), top_bar_rect)
        pygame.draw.line(surface, BORDER_COLOR, (0, TOP_BAR_H), (w, TOP_BAR_H), 1)

        # Back button (top-left)
        self.back_rect = draw_button(surface, "< Menu", (PAD, 16, 110, 40),
                                     text_size=16, border_color=BORDER_COLOR)

        # Cert badge (gradient violet→pink, inline with back button)
        cert_label = str(self.cert_name)
        badge_font = get_font(19, bold=True)
        bw = badge_font.size(cert_label)[0] + 30
        bh = 36
        badge_rect = pygame.Rect(self.back_rect.right + 12, (TOP_BAR_H - bh) // 2, bw, bh)
        draw_gradient_rect(surface, badge_rect, ACCENT_PURPLE, ACCENT_PINK,
                           radius=8, direction="horizontal")
        # Soft halo
        halo = _get_glow_surface(bw, bh, ACCENT_PURPLE, radius=10, alpha=60)
        surface.blit(halo, (badge_rect.x - 10, badge_rect.y - 10))
        draw_gradient_rect(surface, badge_rect, ACCENT_PURPLE, ACCENT_PINK,
                           radius=8, direction="horizontal")
        draw_text(surface, cert_label, badge_rect.centerx, badge_rect.centery,
                  (255, 255, 255), 19, bold=True, anchor="center")

        # Lesson (category) name next to badge
        sc = self.state.current_shortcut
        cat_text = (sc or {}).get('category', '') if sc else ''
        if self.custom_mode:
            total = len(self._custom_playlist)
            current = min(self._custom_index, total)
            cat_text = f"CUSTOM  {current} / {total}"
        draw_text(surface, cat_text or '', badge_rect.right + 14, TOP_BAR_H // 2,
                  TEXT_SECONDARY if not self.custom_mode else ACCENT_PURPLE,
                  18, bold=self.custom_mode, anchor="midleft", max_width=340)

        # Score + Combo (right side)
        score_val = int(round(self._display_score))
        score_str = f"{score_val:,}".replace(",", " ")
        score_size = 38 + int(6 * self._score_flash_t)
        score_y = TOP_BAR_H // 2 - 6
        # Gradient: text primary → violet
        score_rect = draw_text_gradient(
            surface, score_str, w - PAD, score_y,
            [(0.0, TEXT_PRIMARY), (1.0, ACCENT_PURPLE)],
            size=score_size, bold=True, anchor="midright", mono=True,
            glow_color=ACCENT_PURPLE,
            glow_alpha=int(40 + 40 * self._score_flash_t),
        )
        # Shared label Y for SCORE and COMBO — stays fixed regardless of
        # flash-induced size changes on the value rects.
        label_y = score_y + 18
        draw_text(surface, "SCORE", w - PAD, label_y,
                  TEXT_DIM, 13, bold=True, anchor="topright")

        # Combo display (right of center, before score)
        combo_x = score_rect.x - 18
        pygame.draw.line(surface, BORDER_COLOR,
                         (combo_x, 14), (combo_x, TOP_BAR_H - 14), 1)
        combo_x -= 18
        combo_val = self.state.combo
        combo_color = TEXT_DIM
        for th in sorted(COMBO_COLORS.keys(), reverse=True):
            if combo_val >= th:
                combo_color = COMBO_COLORS[th]
                break
        combo_text = f"x{combo_val}" if combo_val >= 2 else "—"
        # popIn: scale 1.1 → 1.0 during bump
        bump_scale = 1.0 + 0.18 * self._combo_bump_t
        combo_size = int(36 * bump_scale)
        if combo_val >= 5:
            draw_text_glow(surface, combo_text, combo_x, score_y, combo_color,
                           size=combo_size, bold=True, anchor="midright",
                           glow_alpha=50)
        else:
            draw_text(surface, combo_text, combo_x, score_y, combo_color,
                      combo_size, bold=True, anchor="midright")
        draw_text(surface, "COMBO", combo_x, label_y,
                  TEXT_DIM, 13, bold=True, anchor="topright")

        # Timer bar (center of top bar, between lesson name and combo)
        timer_x0 = max(badge_rect.right + 200, cat_text and
                       (badge_rect.right + 12 + get_font(15, bold=self.custom_mode)
                        .size(cat_text or '')[0] + 20) or (badge_rect.right + 100))
        timer_x1 = combo_x - 120
        if timer_x1 > timer_x0 + 120:
            timer_w = timer_x1 - timer_x0
            timer_y = TOP_BAR_H // 2 + 6
            # Label row
            draw_text(surface, "TIMER", timer_x0, timer_y - 20,
                      TEXT_DIM, 13, bold=True, anchor="topleft")
            # Compute ratio
            if self.timer_enabled:
                elapsed = now - self.state.timer_start
                ratio = max(0.0, 1.0 - elapsed / self.state.timer_duration)
                remaining_s = max(0.0, self.state.timer_duration - elapsed)
                time_str = f"{remaining_s:.1f}s" if ratio > 0 else "× TIMEOUT"
            else:
                ratio = 1.0
                time_str = "∞"
            time_col = ACCENT_RED if ratio < 0.25 else TEXT_DIM
            draw_text(surface, time_str, timer_x0 + timer_w, timer_y - 20,
                      time_col, 13, bold=True, anchor="topright")
            # Bar
            tb_rect = pygame.Rect(timer_x0, timer_y, timer_w, 6)
            pygame.draw.rect(surface, BG_PANEL, tb_rect, border_radius=3)
            if ratio > 0:
                # Smooth fade: TIMER_LOW → TIMER_MID → TIMER_FULL along ratio.
                # Stops are positioned so each color has a plateau, with a
                # soft transition zone in between (no hard jump at 0.25/0.5).
                fill_col = lerp_color_stops([
                    (0.0,  TIMER_LOW),
                    (0.25, TIMER_LOW),
                    (0.40, TIMER_MID),
                    (0.55, TIMER_MID),
                    (0.70, TIMER_FULL),
                ], ratio)
                # Pulse when <25%
                pulse_alpha = 1.0
                if ratio < 0.25 and not self.state.is_frozen():
                    pulse_alpha = 0.45 + 0.55 * abs(math.sin(now * 6))
                fw = max(1, int(timer_w * ratio))
                fill_surf = pygame.Surface((fw, 6), pygame.SRCALPHA)
                pygame.draw.rect(fill_surf, (*fill_col, int(255 * pulse_alpha)),
                                 (0, 0, fw, 6), border_radius=3)
                surface.blit(fill_surf, tb_rect.topleft)
                # Edge glow
                if fw > 10:
                    gs = pygame.Surface((16, 16), pygame.SRCALPHA)
                    pygame.draw.circle(gs, (*fill_col, 180), (8, 8), 6)
                    surface.blit(gs, (timer_x0 + fw - 8, timer_y - 5),
                                 special_flags=pygame.BLEND_RGBA_ADD)
                # Border glow when critical (screen edges pulse red)
                if ratio < 0.25 and not self.state.is_frozen() and not self.game_over:
                    draw_border_glow(surface, ACCENT_RED,
                                     pulse_alpha * 0.5)

        # Active effects (below top bar, left side)
        effects_y = TOP_BAR_H + 8
        if self.state.is_frozen():
            remaining = self.state.freeze_until - now
            draw_text_glow(surface, f"❄ FREEZE {remaining:.1f}s",
                           PAD, effects_y, ACCENT_CYAN, size=17, bold=True,
                           anchor="topleft", glow_alpha=50)
        if self.state.is_double():
            remaining = self.state.double_until - now
            draw_text_glow(surface, f"×2 {remaining:.1f}s",
                           PAD + 200, effects_y, ACCENT_GOLD, size=17, bold=True,
                           anchor="topleft", glow_alpha=50)

        # ── MAIN 2-COLUMN AREA ────────────────────────────────────────────
        sc = self.state.current_shortcut
        MAIN_TOP = TOP_BAR_H + 40       # leave space for effects row
        MAIN_BOT = h - KB_H - 12        # keyboard strip sits below
        main_h = MAIN_BOT - MAIN_TOP
        left_x = PAD
        right_x = left_x + LEFT_W + GAP * 2
        right_w = w - right_x - PAD

        if sc:
            # ── LEFT COLUMN — Question card ──────────────────────────────
            qcard = pygame.Rect(left_x, MAIN_TOP, LEFT_W, main_h - 90)
            draw_shadow_rect(surface, qcard, BG_CARD, radius=14, border=1,
                             border_color=BORDER_COLOR, shadow_offset=3, shadow_alpha=40)
            # Left gradient bar
            bar_rect = pygame.Rect(qcard.x, qcard.y + 12, 3, qcard.h - 24)
            draw_gradient_rect(surface, bar_rect, ACCENT_PURPLE, ACCENT_PINK,
                               radius=2, direction="vertical")

            qx = qcard.x + 22
            qy = qcard.y + 20
            draw_text(surface, "RACCOURCI CLAVIER", qx, qy, TEXT_DIM, 14,
                      bold=True, anchor="topleft")
            qy += 26

            # Command name — wrap on up to 2 lines (no ellipsis truncation)
            cmd_name = sc.get('command_name', '???')
            cmd_size = 36 if len(cmd_name) <= 22 else (30 if len(cmd_name) <= 32 else 26)
            name_font = get_font(cmd_size, bold=True)
            text_max = qcard.w - 40
            # Word-wrap the command name
            cmd_words = cmd_name.split()
            cmd_lines, cur = [], ""
            for word in cmd_words:
                test = (cur + " " + word).strip()
                if name_font.size(test)[0] > text_max and cur:
                    cmd_lines.append(cur)
                    cur = word
                else:
                    cur = test
            if cur:
                cmd_lines.append(cur)
            # Cap at 2 lines — if more, shrink further and retry once
            if len(cmd_lines) > 2 and cmd_size > 22:
                cmd_size = 22
                name_font = get_font(cmd_size, bold=True)
                cmd_lines, cur = [], ""
                for word in cmd_words:
                    test = (cur + " " + word).strip()
                    if name_font.size(test)[0] > text_max and cur:
                        cmd_lines.append(cur); cur = word
                    else:
                        cur = test
                if cur:
                    cmd_lines.append(cur)
            line_h = cmd_size + 4
            for ln in cmd_lines[:2]:
                draw_text(surface, ln, qx, qy, TEXT_PRIMARY, cmd_size,
                          bold=True, anchor="topleft", shadow=True)
                qy += line_h
            qy += 12

            # Context
            context = sc.get('context') or ''
            if context:
                # Wrap into up to 3 lines
                ctx_font = get_font(17, False)
                words = context.split()
                lines, cur = [], ""
                text_max = qcard.w - 44
                for word in words:
                    test = (cur + " " + word).strip()
                    if ctx_font.size(test)[0] > text_max and cur:
                        lines.append(cur)
                        cur = word
                    else:
                        cur = test
                if cur:
                    lines.append(cur)
                for ln in lines[:3]:
                    draw_text(surface, ln, qx, qy, TEXT_SECONDARY, 17,
                              anchor="topleft")
                    qy += 22
                qy += 8

            # Difficulty dots
            diff = sc.get('difficulty', 1)
            diff_colors = {1: ACCENT_CYAN, 2: ACCENT_ORANGE, 3: ACCENT_RED}
            dot_color = diff_colors.get(diff, TEXT_PRIMARY)
            draw_text(surface, "DIFFICULTÉ", qx, qy, TEXT_DIM, 13,
                      bold=True, anchor="topleft")
            qy += 22
            dr = 5
            dx = qx + dr
            for i in range(3):
                if i < diff:
                    # Soft halo: concentric rings, alpha fades with distance
                    gr = dr * 3
                    glow_s = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
                    steps = 8
                    for k in range(steps):
                        t = k / steps  # 0 at center, ~1 at edge
                        radius = int(dr + (gr - dr) * t)
                        a = int(70 * (1.0 - t) ** 2)
                        if a <= 0: continue
                        pygame.draw.circle(glow_s, (*dot_color, a),
                                           (gr, gr), radius)
                    surface.blit(glow_s, (dx - gr, qy + dr - gr))
                    pygame.draw.circle(surface, dot_color, (dx, qy + dr), dr)
                else:
                    pygame.draw.circle(surface, BORDER_COLOR, (dx, qy + dr), dr, 1)
                dx += dr * 2 + 12

            # Input type hint
            input_type = sc.get('input_type', 'key_combo')
            if input_type == 'key_sequence':
                steps = sc.get('keys_win', [])
                n_steps = len(steps) if isinstance(steps, list) and steps and isinstance(steps[0], list) else 0
                hint_text = f"Sequence ({self._seq_step}/{n_steps})"
                hint_col = ACCENT_PURPLE
            elif input_type == 'modifier_click':
                # Also duplicated in the "APPUYEZ SUR" card (right side) so
                # the click type is visible near both the description and
                # the keycap area.
                is_dbl = sc.get('_detect_click') == 'double'
                hint_text = "+ Double-clic" if is_dbl else "+ Clic souris"
                hint_col = ACCENT_PINK
            elif input_type == 'single_key':
                hint_text = "Touche seule"
                hint_col = TEXT_DIM
            else:
                hint_text = ""
                hint_col = TEXT_DIM
            if hint_text:
                hy = qcard.bottom - 32
                draw_text(surface, hint_text, qx, hy, hint_col, 16,
                          bold=True, anchor="topleft")

            # ── LEFT COLUMN — Unlock Lesson button (hidden in custom) ───
            if self.custom_mode:
                self.cat_unlock_rect = None
                unlock_rect = None
                next_cost = None
            else:
                unlock_y = qcard.bottom + 12
                unlock_rect = pygame.Rect(left_x, unlock_y, LEFT_W, 76)
                self.cat_unlock_rect = unlock_rect
                next_cost = self.state.next_category_unlock_cost()
            if next_cost is not None and unlock_rect is not None:
                next_cat = self.state.next_category_name() or "?"
                can_unlock = self.state.available_score >= next_cost
                prog = self.state.next_category_unlock_progress()
                if can_unlock:
                    # Available — gold outer halo (softly pulses) + dark card
                    pulse = 0.5 + 0.5 * math.sin(now * 3.5)
                    ga = int(35 + 35 * pulse * (0.3 + 0.7 * self._lesson_available_t))
                    draw_glow_rect(surface, unlock_rect, BG_CARD, ACCENT_GOLD,
                                   radius=12, glow_radius=14, glow_alpha=ga)
                    pygame.draw.rect(surface, ACCENT_GOLD, unlock_rect,
                                     width=2, border_radius=12)
                    draw_text(surface, "DÉBLOQUER LEÇON", unlock_rect.x + 16,
                              unlock_rect.y + 10, ACCENT_GOLD, 14, bold=True,
                              anchor="topleft")
                    draw_text(surface, next_cat, unlock_rect.x + 16,
                              unlock_rect.y + 32, TEXT_PRIMARY, 20, bold=True,
                              anchor="topleft", max_width=unlock_rect.w - 120)
                    draw_text(surface, f"-{next_cost} pts", unlock_rect.right - 16,
                              unlock_rect.y + 34, ACCENT_GOLD, 19, bold=True,
                              anchor="topright")
                else:
                    # Locked — padlock + progress bar
                    draw_rounded_rect(surface, unlock_rect, BG_CARD_LOCKED,
                                      radius=12, border=1, border_color=BORDER_COLOR)
                    draw_padlock(surface, unlock_rect.x + 22, unlock_rect.y + 22,
                                 14, TEXT_DIM)
                    draw_text(surface, "PROCHAINE LEÇON", unlock_rect.x + 48,
                              unlock_rect.y + 10, TEXT_DIM, 13, bold=True,
                              anchor="topleft")
                    draw_text(surface, next_cat, unlock_rect.x + 48,
                              unlock_rect.y + 28, TEXT_SECONDARY, 17, bold=True,
                              anchor="topleft", max_width=unlock_rect.w - 140)
                    draw_text(surface, f"{next_cost} pts",
                              unlock_rect.right - 14, unlock_rect.y + 30,
                              TEXT_DIM, 15, bold=True, anchor="topright")
                    # Progress bar
                    pb_rect = pygame.Rect(unlock_rect.x + 14, unlock_rect.bottom - 18,
                                          unlock_rect.w - 28, 6)
                    draw_progress_bar(surface, pb_rect, prog,
                                      [(0.0, ACCENT_PURPLE), (1.0, ACCENT_PINK)],
                                      bg_color=BG_PANEL, radius=3)
            elif unlock_rect is not None:
                self.cat_unlock_rect = None
                # All lessons unlocked — decorative marker (classic mode only)
                draw_rounded_rect(surface, unlock_rect, BG_CARD,
                                  radius=12, border=1, border_color=ACCENT_CYAN)
                draw_text(surface, "TOUTES LES LEÇONS DÉBLOQUÉES",
                          unlock_rect.centerx, unlock_rect.centery,
                          ACCENT_CYAN, 16, bold=True, anchor="center")

            # ── RIGHT COLUMN — "APPUYEZ SUR" card ────────────────────────
            pcard_h = main_h - 140   # leaves space for powers row
            pcard = pygame.Rect(right_x, MAIN_TOP, right_w, pcard_h)
            self._answer_card_rect = pcard
            draw_shadow_rect(surface, pcard, BG_CARD, radius=14, border=1,
                             border_color=BORDER_COLOR, shadow_offset=3, shadow_alpha=40)
            # Corner L-marks
            draw_corner_frame(surface, pcard, ACCENT_PURPLE, length=18,
                              thickness=2, alpha=160)

            label_y = pcard.y + 20
            draw_text(surface, "APPUYEZ SUR", pcard.centerx, label_y,
                      TEXT_DIM, 16, bold=True, anchor="midtop")

            # Keycaps: show `?` if hidden, or real keys if revealed/review
            keys_y = pcard.y + pcard.h // 2 + 6
            show_answer = self.custom_show_answer or self.state.revealed
            fade = self._reveal_fade_t

            if show_answer and fade > 0.02:
                keys_small = sc.get(_KEYS_SMALL, sc.get('keys', []))
                keys_big   = sc.get(_KEYS_BIG,   sc.get('keys', []))
                if not IS_MAC:
                    if input_type == 'key_sequence':
                        keys_big = _to_azerty_display_seq(keys_big)
                    else:
                        keys_big = _to_azerty_display(keys_big)
                cy = pcard.y + pcard.h // 2
                # Secondary (small) reference
                draw_text(surface, _LABEL_SMALL, pcard.centerx,
                          cy - 96, TEXT_DIM, 14,
                          bold=True, anchor="midtop")
                if input_type == 'key_sequence':
                    draw_key_sequence(surface, keys_small, pcard.centerx,
                                      cy - 52, size=28,
                                      current_step=len(keys_small), show_all=True)
                else:
                    draw_key_combo(surface, keys_small, pcard.centerx,
                                   cy - 52, size=28)
                # Primary (big) — player keyboard
                draw_text(surface, _LABEL_BIG, pcard.centerx,
                          cy + 2, _COLOR_BIG, 16,
                          bold=True, anchor="midtop")
                if input_type == 'key_sequence':
                    draw_key_sequence(surface, keys_big, pcard.centerx,
                                      cy + 66, size=40,
                                      current_step=len(keys_big), show_all=True)
                else:
                    draw_key_combo(surface, keys_big, pcard.centerx,
                                   cy + 66, size=40)
                # Alt shortcuts
                if sc.get('alt'):
                    ay = cy + 120
                    for alt in sc.get('alt', [])[:2]:
                        draw_text(surface, "ou", pcard.centerx, ay,
                                  TEXT_DIM, 14, anchor="midtop")
                        ay += 22
                        alt_big = alt.get(_KEYS_BIG, alt.get('keys_win', []))
                        if not IS_MAC:
                            if alt.get('input_type') == 'key_sequence':
                                alt_big = _to_azerty_display_seq(alt_big)
                            else:
                                alt_big = _to_azerty_display(alt_big)
                        draw_key_combo(surface, alt_big, pcard.centerx,
                                       ay + 12, size=24)
                        ay += 38
            else:
                # Live preview: keycaps fill in with whatever the player is
                # currently pressing. Falls back to `?` placeholders when idle.
                preview_keys = self._get_live_preview_keys()
                if preview_keys:
                    # Show QWERTY positional names — matches what Pro Tools
                    # actually receives, not the AZERTY character printed
                    # on the player's keycap.
                    draw_key_combo(surface, preview_keys, pcard.centerx,
                                   keys_y, size=48,
                                   pressed_keys=preview_keys)
                else:
                    qr_size = 78
                    qgap = 20
                    qrects_w = 3 * qr_size + 2 * qgap
                    qx0 = pcard.centerx - qrects_w // 2
                    for i in range(3):
                        r = pygame.Rect(qx0 + i * (qr_size + qgap),
                                        keys_y - qr_size // 2, qr_size, qr_size)
                        pygame.draw.rect(surface, BG_CARD_2, r, border_radius=10)
                        pygame.draw.rect(surface, BORDER_COLOR, r, width=1,
                                         border_radius=10)
                        draw_text(surface, "?", r.centerx, r.centery,
                                  TEXT_DIM, 46, bold=True, anchor="center")
                # Footer hint — for modifier_click shortcuts, show the click
                # type badge in place of the generic "Appuyez sur les touches…"
                if input_type == 'modifier_click':
                    is_dbl = sc.get('_detect_click') == 'double'
                    click_txt = "+ Double-clic" if is_dbl else "+ Clic souris"
                    draw_text(surface, click_txt, pcard.centerx,
                              pcard.bottom - 30, ACCENT_PINK, 16,
                              bold=True, anchor="midtop")
                else:
                    draw_text(surface, "Appuyez sur les touches…", pcard.centerx,
                              pcard.bottom - 30, TEXT_DIM, 16, anchor="midtop")

            # In review/reveal mode, the click-type badge also sits under the
            # revealed keycaps so the player sees what input is expected.
            if show_answer and fade > 0.02 and input_type == 'modifier_click':
                is_dbl = sc.get('_detect_click') == 'double'
                click_txt = "+ Double-clic" if is_dbl else "+ Clic souris"
                draw_text(surface, click_txt, pcard.centerx,
                          pcard.bottom - 30, ACCENT_PINK, 16,
                          bold=True, anchor="midtop")

            # ── RIGHT COLUMN — POWERS row (4 cards, hidden when no bonus) ──
            self.upgrade_rects = {}
            if not self._show_bonus_panel:
                powers_sorted = []
            else:
                powers_sorted = sorted(POWERS.items(), key=lambda kv: kv[1]['order'])
            n = max(1, len(powers_sorted))
            pwr_gap = 10
            pwr_h = main_h - pcard_h - 16
            pwr_w = (right_w - (n - 1) * pwr_gap) / n
            mouse = pygame.mouse.get_pos()
            for i, (pid, pdata) in enumerate(powers_sorted):
                px = right_x + int(i * (pwr_w + pwr_gap))
                pwr_rect = pygame.Rect(px, pcard.bottom + 16, int(pwr_w), pwr_h)
                self.upgrade_rects[pid] = pwr_rect

                unlocked = self.state.is_power_unlocked(pid)
                can_use = self.state.can_use_power(pid)
                hover_t = self._power_hover_t.get(pid, 0.0)
                pcol = pdata['color']

                # Base background
                if unlocked and can_use:
                    base_bg = _lc(BG_CARD, pcol, 0.10 + 0.20 * hover_t)
                    border = _lc(BORDER_COLOR, pcol, 0.4 + 0.6 * hover_t)
                elif unlocked:
                    base_bg = BG_CARD_LOCKED
                    border = BORDER_COLOR
                else:
                    base_bg = BG_CARD_LOCKED
                    border = BORDER_COLOR
                draw_rounded_rect(surface, pwr_rect, base_bg, radius=10,
                                  border=1, border_color=border)

                # Icon circle
                icon_r = 22
                icon_cx = pwr_rect.centerx
                icon_cy = pwr_rect.y + 28
                if unlocked:
                    pygame.draw.circle(surface, _lc(BG_CARD_2, pcol, 0.3),
                                       (icon_cx, icon_cy), icon_r)
                    pygame.draw.circle(surface, pcol, (icon_cx, icon_cy),
                                       icon_r, 2)
                    draw_text(surface, pdata['icon'], icon_cx, icon_cy,
                              pcol if can_use else TEXT_DIM, 17, bold=True,
                              anchor="center")
                else:
                    pygame.draw.circle(surface, BG_CARD_2, (icon_cx, icon_cy),
                                       icon_r)
                    pygame.draw.circle(surface, BORDER_COLOR,
                                       (icon_cx, icon_cy), icon_r, 1)
                    draw_padlock(surface, icon_cx, icon_cy, 16, TEXT_DIM)

                # Name
                name_col = TEXT_PRIMARY if can_use else TEXT_DIM
                draw_text(surface, pdata['name'], pwr_rect.centerx,
                          pwr_rect.y + 56, name_col, 16, bold=True,
                          anchor="midtop")

                # Cost badge or unlock progress
                if unlocked:
                    if self.state.free_upgrades:
                        draw_text(surface, "GRATUIT",
                                  pwr_rect.centerx, pwr_rect.bottom - 18,
                                  ACCENT_PURPLE, 13, bold=True, anchor="midbottom")
                    else:
                        cost_col = ACCENT_GOLD if can_use else TEXT_DIM
                        draw_text(surface, f"-{pdata['use_cost']}",
                                  pwr_rect.centerx, pwr_rect.bottom - 18,
                                  cost_col, 15, bold=True, anchor="midbottom")
                else:
                    prog = self.state.power_unlock_progress(pid)
                    pb = pygame.Rect(pwr_rect.x + 10, pwr_rect.bottom - 12,
                                     pwr_rect.w - 20, 5)
                    draw_progress_bar(surface, pb, prog,
                                      [(0.0, ACCENT_PURPLE), (1.0, ACCENT_PINK)],
                                      bg_color=BG_PANEL, radius=2)
                    draw_text(surface, f"{pdata['unlock_cost']}",
                              pwr_rect.centerx, pwr_rect.bottom - 32,
                              TEXT_DIM, 13, bold=True, anchor="midbottom")

            # Clear legacy action rects (no longer used for v4 click routing)
            self.action_rects = {}

            # ── BOTTOM STRIP — Keyboard + Numpad ─────────────────────────
            pressed_keys = self.kbd.get_current_keys()
            expected_keys = self._get_expected_keys() if self.custom_show_answer else frozenset()
            strip_y = h - KB_H + 6
            strip_h = KB_H - 16
            # Allocate: numpad 160 wide on right, separator 20, keyboard fills rest
            nump_w = 160
            sep_w = 20
            kb_w = w - PAD * 2 - sep_w - nump_w
            kb_x = PAD
            self._draw_keyboard(surface, kb_x, strip_y, kb_w, strip_h,
                                pressed_keys, expected_keys)
            # Separator
            sep_x = kb_x + kb_w + sep_w // 2
            pygame.draw.line(surface, BORDER_COLOR,
                             (sep_x, strip_y + 8),
                             (sep_x, strip_y + strip_h - 8), 1)
            # Numpad
            nump_x = kb_x + kb_w + sep_w
            self._draw_numpad(surface, nump_x, strip_y, nump_w, strip_h,
                              pressed_keys, expected_keys)

        # Achievement notifications
        self._draw_achievements(surface, game_area_w)

        # Particles and popups (on top of everything except game over)
        draw_particles(surface, self.particles)
        draw_score_popups(surface, self.popups)

        # Flash overlay
        if now < self.flash_until and self.flash_color:
            alpha = 0.25 * ((self.flash_until - now) / 0.3)
            draw_flash(surface, self.flash_color, alpha)

        # Game Over
        if self.game_over:
            self._draw_game_over(surface, w, h, game_cx)

    def _draw_game_over(self, surface, w, h, game_cx):
        now = time.time()
        age = now - self.game_over_time

        # Fade-in overlay
        overlay_alpha = min(200, int(age * 600))
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, overlay_alpha))
        surface.blit(overlay, (0, 0))

        if age < 0.15:
            return  # Brief delay before showing box

        # Box slides in from top — height grows with number of alt shortcuts
        box_w = min(520, w - 80)
        n_alts = len(self.game_over_answer.get('alt', [])) if self.game_over_answer else 0
        box_h = 440 + min(2, n_alts) * 46
        box_x = game_cx - box_w // 2
        target_y = (h - box_h) // 2
        slide_t = min(1.0, (age - 0.15) / 0.3)
        ease = 1.0 - (1.0 - slide_t) ** 3  # ease-out
        box_y = int(-box_h + (target_y + box_h) * ease)

        # Box with glow
        draw_glow_rect(surface, (box_x, box_y, box_w, box_h), BG_PANEL,
                       ACCENT_RED, radius=16, glow_radius=20, glow_alpha=40)
        # Border
        pygame.draw.rect(surface, ACCENT_RED,
                         (box_x, box_y, box_w, box_h), width=2, border_radius=16)

        cx = game_cx
        y = box_y + 35

        # Title with glow
        draw_text_glow(surface, "TEMPS ÉCOULÉ", cx, y, ACCENT_RED, size=40,
                       bold=True, anchor="midtop", glow_alpha=60)
        y += 60

        # Answer
        if self.game_over_answer:
            cmd = self.game_over_answer.get('command_name', '?')
            go_small = self.game_over_answer.get(_KEYS_SMALL,
                           self.game_over_answer.get('keys', []))
            go_big   = self.game_over_answer.get(_KEYS_BIG,
                           self.game_over_answer.get('keys', []))
            go_input_type_early = self.game_over_answer.get('input_type', 'key_combo')
            if not IS_MAC:
                if go_input_type_early == 'key_sequence':
                    go_big = _to_azerty_display_seq(go_big)
                else:
                    go_big = _to_azerty_display(go_big)
            draw_text(surface, "La reponse etait :", cx, y, TEXT_SECONDARY, 15,
                      anchor="midtop")
            y += 26
            draw_text(surface, cmd, cx, y, TEXT_PRIMARY, 22, bold=True, anchor="midtop",
                      shadow=True, max_width=box_w - 40)
            y += 30
            go_input_type = self.game_over_answer.get('input_type', 'key_combo')
            draw_text(surface, _LABEL_SMALL, cx, y, TEXT_DIM, 11, bold=True, anchor="midtop")
            y += 16
            if go_input_type == 'key_sequence':
                draw_key_sequence(surface, go_small, cx, y + 16, size=22,
                                  current_step=len(go_small), show_all=True)
            else:
                draw_key_combo(surface, go_small, cx, y + 16, size=22)
            y += 40
            draw_text(surface, _LABEL_BIG, cx, y, _COLOR_BIG, 13, bold=True, anchor="midtop")
            y += 20
            if go_input_type == 'key_sequence':
                draw_key_sequence(surface, go_big, cx, y + 22, size=30,
                                  current_step=len(go_big), show_all=True)
            else:
                draw_key_combo(surface, go_big, cx, y + 22, size=30)
            y += 52

            # Display alternative shortcuts — compact: just the player's
            # keyboard notation (big). The dual reference/player display is
            # already shown for the main shortcut above, so alts don't need
            # to be duplicated.
            for alt in self.game_over_answer.get('alt', [])[:2]:
                draw_text(surface, "ou", cx, y, TEXT_DIM, 11, anchor="midtop")
                y += 14
                alt_big = alt.get(_KEYS_BIG, alt.get('keys_win', []))
                if not IS_MAC:
                    if alt.get('input_type') == 'key_sequence':
                        alt_big = _to_azerty_display_seq(alt_big)
                    else:
                        alt_big = _to_azerty_display(alt_big)
                draw_key_combo(surface, alt_big, cx, y + 10, size=22)
                y += 32

        # Separator
        y += 8
        pygame.draw.line(surface, BORDER_COLOR, (box_x + 30, y), (box_x + box_w - 30, y), 1)
        y += 18

        # Stats
        draw_text_glow(surface, f"Score : {self.state.available_score}",
                       cx, y, ACCENT_GOLD, size=28, bold=True, anchor="midtop", glow_alpha=30)
        y += 36
        draw_text(surface, f"Réussis : {self.state.total_correct}   |   "
                  f"Ratés : {self.state.total_wrong}   |   "
                  f"Max combo : {self.state.max_combo}",
                  cx, y, TEXT_SECONDARY, 14, anchor="midtop")

        # Buttons
        btn_w = 190
        btn_h = 48
        gap = 24
        bx = cx - btn_w - gap // 2
        by = box_y + box_h - btn_h - 28

        mouse = pygame.mouse.get_pos()

        # Smooth hover fade (ALP-style) — compute local dt from last call
        dt = max(0.0, min(0.1, now - self._go_last_draw)) if self._go_last_draw else 0.016
        self._go_last_draw = now

        # Restart — stays cyan/green (primary, positive action)
        restart_rect = pygame.Rect(bx, by, btn_w, btn_h)
        self.game_over_restart_rect = restart_rect
        r_col = ACCENT_GREEN
        self._go_restart_hover_t += (
            (1.0 if restart_rect.collidepoint(mouse) else 0.0)
            - self._go_restart_hover_t
        ) * _lf(0.14, dt)
        rht = self._go_restart_hover_t
        draw_glow_rect(surface, restart_rect, _lc(BG_CARD, r_col, rht),
                       r_col, radius=10, glow_radius=10, glow_alpha=int(rht * 60))
        pygame.draw.rect(surface, r_col, restart_rect, width=2, border_radius=10)
        draw_text(surface, "Recommencer", restart_rect.centerx, restart_rect.centery,
                  _lc(r_col, BG_COLOR, rht), 20, bold=True, anchor="center")

        # Menu — violet (ACCENT_PURPLE) for clear contrast against the cyan
        # Restart button (was ACCENT_BLUE — too close to cyan visually).
        menu_rect = pygame.Rect(bx + btn_w + gap, by, btn_w, btn_h)
        self.game_over_menu_rect = menu_rect
        m_col = ACCENT_PURPLE
        self._go_menu_hover_t += (
            (1.0 if menu_rect.collidepoint(mouse) else 0.0)
            - self._go_menu_hover_t
        ) * _lf(0.14, dt)
        mht = self._go_menu_hover_t
        draw_glow_rect(surface, menu_rect, _lc(BG_CARD, m_col, mht),
                       m_col, radius=10, glow_radius=10, glow_alpha=int(mht * 60))
        pygame.draw.rect(surface, m_col, menu_rect, width=2, border_radius=10)
        draw_text(surface, "Menu", menu_rect.centerx, menu_rect.centery,
                  _lc(m_col, BG_COLOR, mht), 20, bold=True, anchor="center")

    def _draw_achievements(self, surface, game_area_w):
        """Draw the achievement notification banner (top-right of game area)."""
        now = time.time()
        # Expire old notifications
        self._achievement_queue = [n for n in self._achievement_queue
                                   if now - n['born'] < 4.0]
        if not self._achievement_queue:
            return

        notif = self._achievement_queue[0]
        age = now - notif['born']
        info = ACHIEVEMENTS.get(notif['id'], {'name': notif['id'], 'desc': ''})

        # Slide in/out animation
        notif_w = 240
        notif_h = 54
        target_x = game_area_w - notif_w - 16
        hidden_x = game_area_w + 10

        if age < 0.35:
            t = age / 0.35
            ease = 1.0 - (1.0 - t) ** 3
            nx = int(hidden_x + (target_x - hidden_x) * ease)
            alpha = int(255 * ease)
        elif age < 3.3:
            nx = target_x
            alpha = 255
        else:
            t = (age - 3.3) / 0.7
            ease = t ** 2
            nx = int(target_x + (hidden_x - target_x) * ease)
            alpha = int(255 * (1.0 - ease))

        notif_y = 60
        notif_surf = pygame.Surface((notif_w, notif_h), pygame.SRCALPHA)

        # Background
        pygame.draw.rect(notif_surf, (*BG_CARD, min(255, alpha)),
                         (0, 0, notif_w, notif_h), border_radius=8)
        pygame.draw.rect(notif_surf, (*ACCENT_GOLD, min(255, alpha)),
                         (0, 0, notif_w, notif_h), width=1, border_radius=8)
        # Left gold bar
        pygame.draw.rect(notif_surf, (*ACCENT_GOLD, min(255, alpha)),
                         (0, 8, 3, notif_h - 16), border_radius=2)

        # Text
        name_col = (*ACCENT_GOLD, min(255, alpha))
        desc_col = (*TEXT_SECONDARY, min(255, alpha))
        tag_col = (*TEXT_DIM, min(255, alpha))

        # "SUCCES" label
        tag_surf = _scale_alpha(
            get_font(9, True).render("SUCCES", True, tag_col[:3]), alpha)
        notif_surf.blit(tag_surf, (12, 8))

        name_surf = _scale_alpha(
            get_font(14, True).render(info['name'], True, name_col[:3]), alpha)
        notif_surf.blit(name_surf, (12, 20))

        desc_surf = _scale_alpha(
            get_font(11, False).render(info['desc'], True, desc_col[:3]), alpha)
        notif_surf.blit(desc_surf, (12, 36))

        surface.blit(notif_surf, (nx, notif_y))

    def _get_expected_keys(self):
        """Return frozenset of internal key names expected for the current shortcut step."""
        sc = self.state.current_shortcut
        if not sc:
            return frozenset()
        input_type = sc.get('_detect_input_type', 'key_combo')
        if input_type == 'key_sequence':
            steps = sc.get('_detect_steps', [])
            if self._seq_step < len(steps):
                opts = steps[self._seq_step].get('_detect_key_options', [])
                if opts:
                    return opts[0]  # show first option as reference
            return frozenset()
        opts = sc.get('_detect_key_options', [])
        return opts[0] if opts else frozenset()

    def _draw_keyboard(self, surface, kb_x, kb_y, kb_w, kb_h, highlight_keys, expected_keys):
        """Draw the visual QWERTY Mac keyboard.

        highlight_keys: set of internal names currently pressed (player input) → violet
        expected_keys:  set of internal names for the correct shortcut → cyan (review only)
        Both pressed and expected → pink.
        """
        gap = 4
        n_rows = len(_KB_ROWS)
        key_h = int((kb_h - (n_rows - 1) * gap) / n_rows)
        row_h = key_h + gap
        unit_px = (kb_w - (_KB_TOTAL_UNITS - 1) * gap) / _KB_TOTAL_UNITS

        for row_i, row in enumerate(_KB_ROWS):
            row_units = sum(k[2] for k in row)
            row_w = row_units * unit_px + (len(row) - 1) * gap
            rx = kb_x + (kb_w - row_w) / 2
            ry = kb_y + row_i * row_h

            for label, name, units in row:
                kw = int(units * unit_px)
                krect = pygame.Rect(int(rx), int(ry), kw, key_h)

                pressed = name is not None and name in highlight_keys
                expected = name is not None and name in expected_keys

                if pressed and expected:
                    bg = _lc(BG_CARD, ACCENT_PINK, 0.65)
                    border = ACCENT_PINK
                    text_col = TEXT_PRIMARY
                elif pressed:
                    bg = _lc(BG_CARD, ACCENT_PURPLE, 0.55)
                    border = ACCENT_PURPLE
                    text_col = TEXT_PRIMARY
                elif expected:
                    bg = _lc(BG_CARD, ACCENT_CYAN, 0.3)
                    border = _lc(BORDER_COLOR, ACCENT_CYAN, 0.6)
                    text_col = _lc(TEXT_DIM, ACCENT_CYAN, 0.7)
                else:
                    bg = BG_CARD
                    border = BORDER_COLOR
                    text_col = TEXT_DIM

                pygame.draw.rect(surface, bg, krect, border_radius=4)
                pygame.draw.rect(surface, border, krect, width=1, border_radius=4)

                lbl_size = max(9, min(14, int(key_h * 0.45)))
                if len(label) > 3:
                    lbl_size = max(8, lbl_size - 3)
                draw_text(surface, label, krect.centerx, krect.centery,
                          text_col, lbl_size, anchor="center")

                rx += kw + gap

    def _draw_numpad(self, surface, nx, ny, nw, nh, highlight_keys, expected_keys):
        """Draw the numeric keypad on the right side of the bottom strip.

        Uses _NUMPAD_KEYS layout: (label, name, col, row, colspan, rowspan).
        Grid is 4 cols × 5 rows.
        """
        gap = 4
        cols = 4
        rows = 5
        cell_w = int((nw - (cols - 1) * gap) / cols)
        cell_h = int((nh - (rows - 1) * gap) / rows)

        for label, name, col, row, colspan, rowspan in _NUMPAD_KEYS:
            kx = nx + col * (cell_w + gap)
            ky = ny + row * (cell_h + gap)
            kw = cell_w * colspan + gap * (colspan - 1)
            kh = cell_h * rowspan + gap * (rowspan - 1)
            krect = pygame.Rect(kx, ky, kw, kh)

            pressed = name in highlight_keys
            expected = name in expected_keys

            if pressed and expected:
                bg = _lc(BG_CARD, ACCENT_PINK, 0.65)
                border = ACCENT_PINK
                text_col = TEXT_PRIMARY
            elif pressed:
                bg = _lc(BG_CARD, ACCENT_PURPLE, 0.55)
                border = ACCENT_PURPLE
                text_col = TEXT_PRIMARY
            elif expected:
                bg = _lc(BG_CARD, ACCENT_CYAN, 0.3)
                border = _lc(BORDER_COLOR, ACCENT_CYAN, 0.6)
                text_col = _lc(TEXT_DIM, ACCENT_CYAN, 0.7)
            else:
                bg = BG_CARD
                border = BORDER_COLOR
                text_col = TEXT_DIM

            pygame.draw.rect(surface, bg, krect, border_radius=4)
            pygame.draw.rect(surface, border, krect, width=1, border_radius=4)

            lbl_size = max(10, min(15, int(cell_h * 0.5)))
            draw_text(surface, label, krect.centerx, krect.centery,
                      text_col, lbl_size, bold=True, anchor="center")
