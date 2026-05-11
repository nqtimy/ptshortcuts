"""Game screens: Menu and Game — with explosive visual effects."""

import math
import random
import time
import webbrowser

import pygame

from game.config import *

# Platform-aware reveal labels
# On Mac: player presses Mac keys → show keys_mac prominently
# On Windows: player presses AZERTY → show keys_win prominently
if IS_MAC:
    _LABEL_SMALL = "Reference Windows"
    _LABEL_BIG   = "Ton clavier (Mac)"
    _KEYS_SMALL  = 'keys_win'
    _KEYS_BIG    = 'keys_mac'
    _COLOR_BIG   = ACCENT_GREEN
else:
    _LABEL_SMALL = "Examen (QWERTY Mac)"
    _LABEL_BIG   = "Ton clavier (AZERTY)"
    _KEYS_SMALL  = 'keys_mac'
    _KEYS_BIG    = 'keys_win'
    _COLOR_BIG   = ACCENT_BLUE
_DBLCLICK_THRESHOLD = 0.4  # seconds max between two clicks for a double-click

# QWERTY position name → AZERTY character displayed at the same physical key.
# Used only for DISPLAY on the "Ton clavier (AZERTY)" side. Detection still
# uses QWERTY positional names everywhere (scan-code based).
_QWERTY_TO_AZERTY_DISPLAY = {
    'Q': 'A', 'W': 'Z', 'A': 'Q', 'Z': 'W', 'M': ',',
    ';': 'M', "'": 'ù', ',': ';', '.': ':', '/': '!',
    '[': '^', ']': '$', '\\': '*', '`': '²',
    '-': ')', '=': '=',
}

def _to_azerty_display(keys):
    """Translate a flat list of key names from QWERTY-positional to AZERTY
    characters (display only). Preserves modifiers, function keys, numpad,
    arrows, digits unchanged. On Mac, this is a no-op at call sites because
    _KEYS_BIG is 'keys_mac' there."""
    if not keys:
        return keys
    return [_QWERTY_TO_AZERTY_DISPLAY.get(k, k) for k in keys]

def _to_azerty_display_seq(steps):
    """Same as _to_azerty_display but for key_sequence (list of lists)."""
    if not steps:
        return steps
    return [_to_azerty_display(step) for step in steps]

from game.loader import get_shortcuts_for_categories, get_weighted_shortcuts
from game.particles import (
    ScorePopup, RingParticle, spawn_explosion, spawn_sparks,
    spawn_firework_ring, spawn_embers, spawn_wrong_burst,
)
from game.renderer import (
    draw_border_glow, draw_button, draw_combo_text, draw_flash, draw_glow_rect,
    draw_key_combo, draw_key_sequence, draw_particles, draw_rounded_rect,
    draw_score_popups, draw_shadow_rect, draw_text, draw_text_glow,
    draw_timer_bar, draw_vignette, get_font,
    # Design v4 helpers
    draw_text_gradient, draw_gradient_rect, draw_radial_halo, draw_padlock,
    draw_progress_bar, draw_corner_frame,
    ease_out_cubic, lerp_color, lerp_color_stops, frame_lerp,
    _get_glow_surface, _scale_alpha,
)
from game.achievements import ACHIEVEMENTS
from game.leaderboard import save_local_highscore, submit_score_async
from game.state import (GameState, load_game, save_game, load_pseudo, save_pseudo,
                        reset_all_data, load_stats, load_achievements, save_achievements)


# ---------------------------------------------------------------------------
# Menu Screen
# ---------------------------------------------------------------------------

def _lc(c1, c2, t):
    """Linearly interpolate between two RGB colors."""
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def _lf(k, dt):
    """Frame-rate independent lerp factor. k is the per-frame factor at 60 fps."""
    return 1.0 - (1.0 - k) ** (dt * 60.0)


# Certification display order
CERT_ORDER = ['101', '110', '130', '201', '210M', '210P', '205D', '210D']

# Certifications not yet playable
COMING_SOON = {'210P', '205D', '210D'}

# Difficulty levels
DIFFICULTY_LABELS = {
    1: ('Facile', ACCENT_GREEN),
    2: ('Intermediaire', ACCENT_ORANGE),
    3: ('Difficile', ACCENT_RED),
}


class MenuScreen:
    """Certification selection screen with carousel navigation."""

    def __init__(self, certifications):
        self.certifications = certifications
        # Order certs according to CERT_ORDER, then any extras alphabetically
        ordered = [c for c in CERT_ORDER if c in certifications]
        extras = sorted(c for c in certifications if c not in ordered)
        self.cert_names = ordered + extras
        self._playable_certs = [c for c in self.cert_names if c not in COMING_SOON]
        self.cert_index = 0
        self.difficulty = 1  # 1, 2 or 3
        # Custom mode (replaces the former "review mode") — configurable revision sandbox.
        self.custom_mode = False
        self.timer_enabled = True
        self.custom_bonus = False        # bonus/upgrades enabled (gratuits)
        self.custom_show_answer = False  # shortcut visible en permanence
        self.custom_random = True        # ON = shuffle ; OFF = ordre par difficulté
        self.custom_certs = set()        # certs cochées dans le checklist
        # Selected* fields: snapshot when JOUER is clicked, consumed by main.py.
        self.selected = None             # cert name (single) OR list of cert names (custom)
        self.selected_difficulty = None
        self.selected_custom = False
        self.selected_timer = True
        self.selected_bonus = False
        self.selected_show_answer = False
        self.selected_random = True
        self.selected_certs = []
        self.show_stats = False
        self.show_leaderboard = False
        self.birth = time.time()

        # Animations
        self._waveform_phases = [random.uniform(0, math.pi * 2) for _ in range(40)]
        self._waveform_speeds = [random.uniform(1.8, 4.0) for _ in range(40)]
        self._bg_particles = []   # [x, y, vx, vy, alpha_scale, color_idx]
        self._particle_layer = None
        self._play_gravity = [0.0, 0.0]
        self._custom_mode_t = 0.0  # 0.0 = normal (blue), 1.0 = custom mode (red)
        self._cert_slide_pos = 0.0     # actual rendered x offset (never jumps)
        self._cert_slide_target = 0.0  # target x offset (can jump on press)
        self._cert_left_hover_t = 0.0
        self._cert_right_hover_t = 0.0
        # Hover fade interpolation values (0.0 = idle, 1.0 = fully hovered)
        self._pill_hover_t = [0.0, 0.0, 0.0]
        self._custom_hover_t = 0.0
        self._play_hover_t = 0.0
        self._alp_hover_t = 0.0
        self._vibe_hover_t = 0.0
        # Custom-mode hover fades (keyed by option / cert name).
        self._opt_hover_t = {}
        self._cert_check_hover_t = {}
        # Custom-mode toggle animations (0..1 lerp toward active state).
        self._opt_anim_t = {}
        self._cert_anim_t = {}
        # Mode-toggle crossfade: capture a snapshot of the panel area each
        # frame; when the user flips the mode, we freeze the previous-mode
        # snapshot and overlay it with decreasing alpha for ~0.3s.
        self._prev_custom_mode = False
        self._panel_snapshot = None       # snapshot of last frame's panel
        self._panel_snapshot_top = 0
        self._transition_fade_snap = None # frozen snap during transition
        self._transition_start = -10.0    # epoch; far past = not transitioning

        # Button rects for hit-testing
        self._cert_left_rect = None
        self._cert_right_rect = None
        self._diff_pill_rects = [None, None, None]
        self._play_rect = None
        self._custom_rect = None
        self._alp_rect = None
        self._vibe_rect = None
        self._pseudo_rect = None
        # Custom-mode UI rects (set in draw, read in handle_event).
        self._opt_rects = {}        # {option_id: pygame.Rect}
        self._cert_check_rects = {} # {cert_name: pygame.Rect}

        # Pseudo (player name)
        self._pseudo = load_pseudo()          # persisted value
        self._pseudo_editing = False          # True when field is focused
        self._pseudo_input = ''              # edit buffer
        self._pseudo_hover_t = 0.0

        # Reset confirmation
        self._reset_confirm = False
        self._reset_btn_rect = None
        self._reset_yes_rect = None
        self._reset_no_rect = None
        self._reset_hover_t = 0.0
        self._reset_yes_hover_t = 0.0
        self._reset_no_hover_t = 0.0

        # Default custom checklist: first playable cert (or none).
        if self._playable_certs:
            self.custom_certs.add(self._playable_certs[0])

    @property
    def current_cert(self):
        return self.cert_names[self.cert_index]

    def _pseudo_confirm(self):
        """Validate and save the pseudo input buffer."""
        text = self._pseudo_input.strip()
        if len(text) >= 3:
            self._pseudo = text
            save_pseudo(text)
        self._pseudo_editing = False
        self._pseudo_input = ''

    def _pseudo_cancel(self):
        self._pseudo_editing = False
        self._pseudo_input = ''

    def _can_play(self):
        """Whether the JOUER button is currently actionable."""
        if self.custom_mode:
            return any(c not in COMING_SOON for c in self.custom_certs)
        return self.current_cert not in COMING_SOON

    def _commit_selection(self):
        """Snapshot menu state into selected_* fields (consumed by main.py)."""
        self.selected_difficulty = self.difficulty
        self.selected_custom = self.custom_mode
        self.selected_timer = self.timer_enabled
        self.selected_bonus = self.custom_bonus
        self.selected_show_answer = self.custom_show_answer
        self.selected_random = self.custom_random
        if self.custom_mode:
            chosen = [c for c in self.cert_names
                      if c in self.custom_certs and c not in COMING_SOON]
            if not chosen:
                return
            self.selected_certs = chosen
            self.selected = chosen  # list = custom mode signal
        else:
            self.selected_certs = [self.current_cert]
            self.selected = self.current_cert

    def _merged_custom_cert_data(self):
        """Aggregate selected custom certs into a virtual cert_data dict."""
        all_sc = []
        cats = []
        for cname in self.cert_names:
            if cname in self.custom_certs and cname in self.certifications:
                cd = self.certifications[cname]
                all_sc.extend(cd.get('all_shortcuts', []))
                cats.extend(cd.get('category_names', []))
        return {'all_shortcuts': all_sc, 'category_names': cats}

    def _draw_custom_panel(self, surface, w, top, dt, mouse, page_accent, page_accent2):
        """Draw the custom-mode options panel (replaces carousel + pills).

        Returns the y coordinate where the bottom-controls separator should start.
        """
        self._opt_rects.clear()
        self._cert_check_rects.clear()
        original_top = top  # keep for return calculation

        draw_text(surface, "MODE CUSTOM — RÉVISION LIBRE", w // 2, top,
                  TEXT_DIM, 12, bold=True, anchor="midtop")
        top += 22

        # Two-column layout: options on the left, cert checklist on the right.
        col_w = min(360, (w - 100) // 2)
        col_gap = 30
        total_w = col_w * 2 + col_gap
        left_x = (w - total_w) // 2
        right_x = left_x + col_w + col_gap

        draw_text(surface, "Options", left_x + col_w // 2, top,
                  TEXT_SECONDARY, 15, bold=True, anchor="midtop")
        draw_text(surface, "Certifications", right_x + col_w // 2, top,
                  TEXT_SECONDARY, 15, bold=True, anchor="midtop")
        col_y = top + 22

        # ── Left column: 4 option toggles ──
        opt_h = 36
        opt_gap = 6
        options = [
            ('timer',       'Timer',                  self.timer_enabled),
            ('bonus',       'Bonus (gratuits)',       self.custom_bonus),
            ('show_answer', 'Afficher les réponses',  self.custom_show_answer),
            ('random',      'Ordre aléatoire',        self.custom_random),
        ]
        opt_y = col_y
        for opt_id, lbl, val in options:
            rect = pygame.Rect(left_x, opt_y, col_w, opt_h)
            self._opt_rects[opt_id] = rect
            is_hov = rect.collidepoint(mouse)
            ht = self._opt_hover_t.get(opt_id, 0.0)
            ht += ((1.0 if is_hov else 0.0) - ht) * _lf(0.14, dt)
            self._opt_hover_t[opt_id] = ht

            # Animated toggle: knob slides smoothly between off/on positions
            # (sub-pixel ease so re-clicking quickly looks fluid, not snappy).
            anim_t = self._opt_anim_t.get(opt_id, 1.0 if val else 0.0)
            anim_target = 1.0 if val else 0.0
            anim_t += (anim_target - anim_t) * _lf(0.22, dt)
            self._opt_anim_t[opt_id] = anim_t

            border_target = _lc(BORDER_COLOR, page_accent, anim_t)
            bg_c = _lc(BG_CARD, BG_CARD_HOVER, ht)
            bc_c = _lc(border_target, page_accent, ht * 0.5)
            draw_shadow_rect(surface, rect, bg_c, radius=8, border=1,
                             border_color=bc_c, shadow_offset=2, shadow_alpha=15)

            # Toggle knob (animated)
            kh = 14
            kw = 28
            kx = rect.x + 12
            ky = rect.centery
            krect = pygame.Rect(kx, ky - kh // 2, kw, kh)
            kbg = _lc(BG_SECONDARY, page_accent, anim_t)
            pygame.draw.rect(surface, kbg, krect, border_radius=kh // 2)
            knob_left = krect.x + kh // 2 + 2
            knob_right = krect.right - kh // 2 - 2
            knob_x = int(knob_left + (knob_right - knob_left) * anim_t)
            knob_color = _lc(TEXT_DIM, TEXT_PRIMARY, anim_t)
            pygame.draw.circle(surface, knob_color, (knob_x, ky), kh // 2 - 2)

            # Always render bold to avoid the thin-stroke pixelation that the
            # static Space Grotesk Regular shows at small sizes — the active vs
            # inactive distinction is conveyed via color instead of weight.
            text_col = _lc(TEXT_SECONDARY, TEXT_PRIMARY, anim_t)
            draw_text(surface, lbl, krect.right + 12, ky, text_col, 15,
                      bold=True, anchor="midleft")
            opt_y += opt_h + opt_gap

        # ── Right column: cert checklist (2-column grid) ──
        cell_w = (col_w - 8) // 2
        cell_h = 30
        cell_gap = 5
        for i, cname in enumerate(self.cert_names):
            col_i = i % 2
            row_i = i // 2
            cx = right_x + col_i * (cell_w + 8)
            cy = col_y + row_i * (cell_h + cell_gap)
            crect = pygame.Rect(cx, cy, cell_w, cell_h)
            is_coming = cname in COMING_SOON
            checked = cname in self.custom_certs

            if not is_coming:
                self._cert_check_rects[cname] = crect

            is_hov = crect.collidepoint(mouse) and not is_coming
            ht = self._cert_check_hover_t.get(cname, 0.0)
            ht += ((1.0 if is_hov else 0.0) - ht) * _lf(0.14, dt)
            self._cert_check_hover_t[cname] = ht

            if is_coming:
                draw_rounded_rect(surface, crect, BG_CARD_LOCKED, radius=6,
                                  border=1, border_color=BORDER_COLOR)
                draw_text(surface, cname, crect.x + 10, crect.centery,
                          TEXT_DIM, 15, bold=True, anchor="midleft")
                draw_text(surface, "Soon", crect.right - 10, crect.centery,
                          TEXT_DIM, 11, bold=True, anchor="midright")
            else:
                # Animated check state: 0 = unchecked, 1 = checked
                anim_t = self._cert_anim_t.get(cname, 1.0 if checked else 0.0)
                anim_target = 1.0 if checked else 0.0
                anim_t += (anim_target - anim_t) * _lf(0.22, dt)
                self._cert_anim_t[cname] = anim_t

                bg_c = _lc(BG_CARD, BG_CARD_HOVER, ht)
                bc_c = _lc(BORDER_COLOR, page_accent, max(ht * 0.5, anim_t))
                draw_shadow_rect(surface, crect, bg_c, radius=6, border=1,
                                 border_color=bc_c, shadow_offset=2, shadow_alpha=15)
                # Checkbox: box fills with the accent as anim_t rises
                bs = 14
                bx = crect.x + 10
                by = crect.centery - bs // 2
                box_rect = pygame.Rect(bx, by, bs, bs)
                box_fill = _lc(BG_SECONDARY, page_accent, anim_t)
                pygame.draw.rect(surface, box_fill, box_rect, border_radius=3)
                box_border = _lc(_lc(BORDER_COLOR, page_accent, ht),
                                 page_accent, anim_t)
                pygame.draw.rect(surface, box_border, box_rect, width=1,
                                 border_radius=3)
                # Check mark — pop-in scale + alpha fade synced to anim_t
                if anim_t > 0.05:
                    pop = min(1.0, anim_t * 1.3)
                    cs_x, cs_y = bs // 2, bs // 2
                    p1 = (cs_x + int((3 - cs_x) * pop),
                          cs_y + int((bs // 2 - cs_y) * pop))
                    p2 = (cs_x + int((bs // 2 - 1 - cs_x) * pop),
                          cs_y + int((bs - 4 - cs_y) * pop))
                    p3 = (cs_x + int((bs - 3 - cs_x) * pop),
                          cs_y + int((3 - cs_y) * pop))
                    cs_surf = pygame.Surface((bs, bs), pygame.SRCALPHA)
                    pygame.draw.lines(cs_surf, BG_COLOR, False, [p1, p2, p3], 2)
                    _csa = int(255 * anim_t)
                    _csov = pygame.Surface((bs, bs), pygame.SRCALPHA)
                    _csov.fill((255, 255, 255, _csa))
                    cs_surf.blit(_csov, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                    surface.blit(cs_surf, (bx, by))
                # Name color follows the toggle progress.
                text_col = _lc(TEXT_SECONDARY, TEXT_PRIMARY, anim_t)
                draw_text(surface, cname, bx + bs + 10, crect.centery,
                          text_col, 15, bold=True, anchor="midleft")

        # Match the classic carousel+pills section height so the separator,
        # mode toggle and JOUER button stay at the same Y when toggling modes.
        # Empirical offset measured against the classic layout's ctrl_top.
        return original_top + 258

    def handle_event(self, event):
        # Pseudo field: consume keyboard events while editing
        if self._pseudo_editing and event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._pseudo_confirm()
            elif event.key == pygame.K_ESCAPE:
                self._pseudo_cancel()
            elif event.key == pygame.K_BACKSPACE:
                self._pseudo_input = self._pseudo_input[:-1]
            else:
                ch = event.unicode
                if ch and ch.isprintable() and len(self._pseudo_input) < 15:
                    # Allow alphanum, space, underscore, dash only
                    if ch.isalnum() or ch in (' ', '_', '-'):
                        self._pseudo_input += ch
            return  # consume all keys while editing

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            # Click on pseudo field to start editing
            if self._pseudo_rect and self._pseudo_rect.collidepoint(pos):
                self._pseudo_editing = True
                self._pseudo_input = self._pseudo
                return
            # Click outside field while editing → confirm
            if self._pseudo_editing:
                self._pseudo_confirm()

            # Reset confirmation buttons
            if self._reset_confirm:
                if self._reset_yes_rect and self._reset_yes_rect.collidepoint(pos):
                    reset_all_data()
                    self._pseudo = ''
                    self._reset_confirm = False
                    return
                elif self._reset_no_rect and self._reset_no_rect.collidepoint(pos):
                    self._reset_confirm = False
                    return
                else:
                    self._reset_confirm = False
                    # fall through to other handlers
            elif self._reset_btn_rect and self._reset_btn_rect.collidepoint(pos):
                self._reset_confirm = True
                return

            # Custom-mode option toggles + cert checklist (only active when custom_mode is on).
            if self.custom_mode:
                hit_opt = False
                for opt_id, orect in self._opt_rects.items():
                    if orect and orect.collidepoint(pos):
                        if opt_id == 'timer':
                            self.timer_enabled = not self.timer_enabled
                        elif opt_id == 'bonus':
                            self.custom_bonus = not self.custom_bonus
                        elif opt_id == 'show_answer':
                            self.custom_show_answer = not self.custom_show_answer
                        elif opt_id == 'random':
                            self.custom_random = not self.custom_random
                        hit_opt = True
                        break
                if hit_opt:
                    return
                for cname, crect in self._cert_check_rects.items():
                    if crect and crect.collidepoint(pos):
                        if cname in self.custom_certs:
                            if len(self.custom_certs) > 1:
                                self.custom_certs.discard(cname)
                        else:
                            self.custom_certs.add(cname)
                        return

            if (not self.custom_mode) and self._cert_left_rect and self._cert_left_rect.collidepoint(pos):
                self.cert_index = (self.cert_index - 1) % len(self.cert_names)
                self._cert_slide_target = -110
            elif (not self.custom_mode) and self._cert_right_rect and self._cert_right_rect.collidepoint(pos):
                self.cert_index = (self.cert_index + 1) % len(self.cert_names)
                self._cert_slide_target = 110
            elif self._custom_rect and self._custom_rect.collidepoint(pos):
                self.custom_mode = not self.custom_mode
            elif self._play_rect and self._play_rect.collidepoint(pos) and self._can_play():
                self._commit_selection()
            elif self._alp_rect and self._alp_rect.collidepoint(pos):
                webbrowser.open("https://alp.avidlearningcentral.com/users/sign_in")
            elif self._vibe_rect and self._vibe_rect.collidepoint(pos):
                webbrowser.open("https://www.youtube.com/playlist?list=PL6NdkXsPL07Il2hEQGcLI4dg_LTg7xA2L")
            elif not self.custom_mode:
                for i, prect in enumerate(self._diff_pill_rects):
                    if prect and prect.collidepoint(pos):
                        self.difficulty = i + 1
                        break

        if event.type == pygame.KEYDOWN:
            # Carrousel + difficulty pills only relevant in classic mode.
            if not self.custom_mode:
                if event.key == pygame.K_LEFT:
                    self.cert_index = (self.cert_index - 1) % len(self.cert_names)
                    self._cert_slide_target = -110
                    return
                elif event.key == pygame.K_RIGHT:
                    self.cert_index = (self.cert_index + 1) % len(self.cert_names)
                    self._cert_slide_target = 110
                    return
                elif event.key == pygame.K_UP:
                    self.difficulty = min(3, self.difficulty + 1)
                    return
                elif event.key == pygame.K_DOWN:
                    self.difficulty = max(1, self.difficulty - 1)
                    return
                elif event.key == pygame.K_1:
                    self.difficulty = 1
                    return
                elif event.key == pygame.K_2:
                    self.difficulty = 2
                    return
                elif event.key == pygame.K_3:
                    self.difficulty = 3
                    return
            if event.key == pygame.K_c:
                self.custom_mode = not self.custom_mode
            elif event.key == pygame.K_s:
                self.show_stats = True
            elif event.key == pygame.K_l:
                self.show_leaderboard = True
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self._can_play():
                    self._commit_selection()

    def _draw_arrow(self, surface, cx, cy, direction, size=18, enabled=True,
                    accent_color=None, hover_t=0.0, mouse_pos=None):
        """Draw a triangle arrow. Returns (hit_rect, is_hovered)."""
        if mouse_pos is None:
            mouse_pos = pygame.mouse.get_pos()
        base = accent_color or ACCENT_BLUE
        bright = tuple(min(255, int(c + (255 - c) * 0.35)) for c in base)
        color = _lc(base, bright, hover_t) if enabled else TEXT_DIM

        rect = pygame.Rect(cx - size - 8, cy - size - 8, (size + 8) * 2, (size + 8) * 2)
        hovered = rect.collidepoint(mouse_pos) and enabled

        if direction == -1:
            raw = [(cx + size // 2, cy - size), (cx - size // 2, cy), (cx + size // 2, cy + size)]
        else:
            raw = [(cx - size // 2, cy - size), (cx + size // 2, cy), (cx - size // 2, cy + size)]

        scale = 1.0 + hover_t * 0.2
        points = [(cx + (px - cx) * scale, cy + (py - cy) * scale) for px, py in raw]
        pygame.draw.polygon(surface, color, points)

        if hover_t > 0.01 and enabled:
            glow = pygame.Surface((size * 4, size * 4), pygame.SRCALPHA)
            pygame.draw.polygon(glow, (*color, int(hover_t * 60)),
                                [(px - cx + size * 2, py - cy + size * 2) for px, py in raw])
            surface.blit(glow, (cx - size * 2, cy - size * 2))

        return rect, hovered

    def draw(self, surface, dt=0.016):
        w, h = surface.get_size()
        now = time.time()
        age = now - self.birth
        mouse = pygame.mouse.get_pos()
        # Slow chrome color transition (~1s) — title glow, card, accents
        # ease between blue→red while the panel content swaps quickly via the
        # snapshot crossfade below. The two animations run independently so
        # spam-toggling never glitches: rmt always lerps toward the current
        # state, and each toggle just freezes the latest panel snapshot.
        self._custom_mode_t += ((1.0 if self.custom_mode else 0.0) - self._custom_mode_t) * _lf(0.07, dt)
        rmt = self._custom_mode_t
        # Design v4: violet/pink in normal mode, red/orange in review mode
        page_accent = _lc(ACCENT_PURPLE, ACCENT_RED, rmt)
        page_accent2 = _lc(ACCENT_PINK, ACCENT_ORANGE, rmt)
        surface.fill(BG_COLOR)
        # Signature violet radial halo at top
        draw_radial_halo(surface, w // 2, 0, int(w * 0.6), 280,
                         page_accent, alpha=int(50 - 10 * rmt), falloff=2.2)

        # ── Ambient background particles ───────────────────────────────────
        if len(self._bg_particles) < 42 and random.random() < _lf(0.18, dt):
            self._bg_particles.append([
                random.randint(0, w), float(h + 4),
                random.uniform(-0.2, 0.2), random.uniform(0.4, 0.9),
                random.uniform(0.2, 0.5), random.randint(0, 1),
            ])
        self._bg_particles = [p for p in self._bg_particles if p[1] > -4]
        speed = dt * 60.0
        for p in self._bg_particles:
            p[0] += p[2] * speed
            p[1] -= p[3] * speed
        if self._bg_particles:
            if self._particle_layer is None or self._particle_layer.get_size() != (w, h):
                self._particle_layer = pygame.Surface((w, h), pygame.SRCALPHA)
            self._particle_layer.fill((0, 0, 0, 0))
            par_x = (mouse[0] - w / 2) / w * 8
            par_y = (mouse[1] - h / 2) / h * 4
            for p in self._bg_particles:
                progress = max(0.0, min(1.0, 1.0 - p[1] / h))
                alpha = int(p[4] * 180 * math.sin(progress * math.pi))
                if alpha > 0:
                    color = page_accent if p[5] == 0 else page_accent2
                    pygame.draw.circle(self._particle_layer, (*color, alpha),
                                       (int(p[0] + par_x), int(p[1] + par_y)), 1)
            surface.blit(self._particle_layer, (0, 0))

        draw_vignette(surface, 0.3)

        # ── Title ─────────────────────────────────────────────────────────
        title_y = int(h * 0.06)
        # Design v4 gradient: white → violet → pink (red/orange in review mode)
        title_stops = [
            (0.0, TEXT_PRIMARY),
            (0.55, page_accent),
            (1.0, page_accent2),
        ]
        draw_text_gradient(surface, "PT Shortcuts", w // 2, title_y + 32, title_stops,
                           size=72, bold=True, anchor="center",
                           glow_color=page_accent, glow_alpha=60)
        draw_text(surface, "Pro Tools Keyboard Trainer", w // 2, title_y + 76,
                  TEXT_SECONDARY, 20, anchor="midtop")

        # ── Animated waveform separator ───────────────────────────────────
        sep_y = title_y + 140
        bar_count = 40
        wave_w = min(500, w - 200)
        bar_spacing = wave_w / bar_count
        bar_w_each = max(2, int(bar_spacing) - 2)
        wave_x0 = w // 2 - wave_w // 2
        bar_max_h = 10
        wave_surf = pygame.Surface((int(wave_w) + bar_w_each + 4, bar_max_h * 2 + 2), pygame.SRCALPHA)
        for i in range(bar_count):
            t = i / max(1, bar_count - 1)
            envelope = math.sin(t * math.pi) ** 1.1
            bar_h_half = int(envelope * (2 + 8 * abs(math.sin(
                now * self._waveform_speeds[i] + self._waveform_phases[i]))))
            if bar_h_half < 1:
                continue
            bx = int(i * bar_spacing)
            r = int(page_accent[0] + (page_accent2[0] - page_accent[0]) * t)
            g = int(page_accent[1] + (page_accent2[1] - page_accent[1]) * t)
            b_c = int(page_accent[2] + (page_accent2[2] - page_accent[2]) * t)
            alpha = int(70 + 80 * envelope)
            bar_rect = (bx, bar_max_h - bar_h_half, bar_w_each, bar_h_half * 2 + 1)
            # Base cylinder body
            pygame.draw.rect(wave_surf, (r, g, b_c, alpha), bar_rect, border_radius=2)
            # Cylinder highlight: left third, lighter
            if bar_w_each >= 4:
                hi_w = max(1, bar_w_each // 3)
                hi_alpha = min(255, alpha + 55)
                pygame.draw.rect(wave_surf,
                                 (min(255, r + 70), min(255, g + 70), min(255, b_c + 35), hi_alpha),
                                 (bx, bar_max_h - bar_h_half, hi_w, bar_h_half * 2 + 1),
                                 border_radius=2)
        surface.blit(wave_surf, (wave_x0, sep_y - bar_max_h))

        # ── Mode-toggle transition: freeze the previous-mode panel snapshot.
        # Detect the toggle BEFORE drawing the new panel so we have a clean
        # before/after pair to crossfade.
        mode_changed = self.custom_mode != self._prev_custom_mode
        if mode_changed:
            self._transition_fade_snap = self._panel_snapshot
            self._transition_start = now
            self._prev_custom_mode = self.custom_mode

        panel_top = sep_y + 24
        panel_h_const = 258  # matches _draw_custom_panel's offset

        # ── Certification Carousel + Pills (or Custom panel) ───────────────
        cert_name = self.current_cert
        cert_data = self.certifications[cert_name]

        if self.custom_mode:
            # Custom mode: replace carousel + pills with checklist + options.
            self._cert_left_rect = None
            self._cert_right_rect = None
            for i in range(3):
                self._diff_pill_rects[i] = None
            ctrl_top = self._draw_custom_panel(
                surface, w, sep_y + 24, dt, mouse, page_accent, page_accent2)
            cert_data = self._merged_custom_cert_data()
            cert_name = "Custom"
            # Skip the rest of this section (carousel + pills).
            self._opt_rects_active = True
        else:
            self._opt_rects.clear()
            self._cert_check_rects.clear()
            self._opt_rects_active = False

        if not self.custom_mode:
            carousel_top = sep_y + 24
            draw_text(surface, "CERTIFICATION", w // 2, carousel_top, TEXT_DIM, 12,
                      bold=True, anchor="midtop")
            carousel_top += 20

            card_w = min(480, w - 160)
            card_h = 120
            card_x = (w - card_w) // 2
            card_rect = pygame.Rect(card_x, carousel_top, card_w, card_h)

            # Entrance animation: ease-out cubic over 1.5s — the card and
            # everything cascading from it (dots, pills, ctrl_top) lift into
            # place with a decelerating velocity curve, like an AE ease-out.
            INTRO_SLIDE_DUR = 1.5
            sp = max(0.0, min(1.0, age / INTRO_SLIDE_DUR))
            sp_eased = 1.0 - (1.0 - sp) ** 3
            slide = 20 * (1.0 - sp_eased)
            card_rect.y += int(slide)

            # Small directional slide (hint only, no saccade)
            self._cert_slide_pos += (self._cert_slide_target - self._cert_slide_pos) * _lf(0.25, dt)
            self._cert_slide_target *= 0.70 ** (dt * 60.0)
            if abs(self._cert_slide_pos) > 0.3:
                card_rect.x += int(self._cert_slide_pos)
            else:
                self._cert_slide_pos = 0.0
                self._cert_slide_target = 0.0

            draw_glow_rect(surface, card_rect, BG_CARD, page_accent,
                           radius=14, glow_radius=12, glow_alpha=25)
            pygame.draw.rect(surface, BORDER_COLOR, card_rect, width=1, border_radius=14)

            # Left gradient accent bar (violet → pink)
            accent_rect = pygame.Rect(card_rect.x + 1, card_rect.y + 14, 4, card_rect.h - 28)
            draw_gradient_rect(surface, accent_rect, page_accent, page_accent2,
                               radius=2, direction="vertical")

            # Design v4 L-shape corner decorations
            draw_corner_frame(surface, card_rect, page_accent, length=16,
                              thickness=2, alpha=180)

            # Cert name
            draw_text(surface, cert_name, card_rect.x + 20, card_rect.y + 18,
                      TEXT_PRIMARY, 52, bold=True, anchor="topleft", shadow=True)

            # Stats (bottom-left)
            n_shortcuts = len(cert_data.get('all_shortcuts', []))
            n_cats = len(cert_data.get('category_names', []))
            stats_y = card_rect.bottom - 28
            draw_text(surface, f"{n_shortcuts} raccourcis", card_rect.x + 20, stats_y,
                      TEXT_SECONDARY, 14, anchor="topleft")
            sep_x = card_rect.x + 20 + get_font(14).size(f"{n_shortcuts} raccourcis")[0] + 10
            pygame.draw.circle(surface, TEXT_DIM, (sep_x, stats_y + 7), 2)
            draw_text(surface, f"{n_cats} categories", sep_x + 14, stats_y,
                      TEXT_DIM, 14, anchor="topleft")

            # Mini difficulty bar chart (right side of card)
            n1 = sum(1 for s in cert_data.get('all_shortcuts', []) if s.get('difficulty', 1) == 1)
            n2 = sum(1 for s in cert_data.get('all_shortcuts', []) if s.get('difficulty', 1) == 2)
            n3 = sum(1 for s in cert_data.get('all_shortcuts', []) if s.get('difficulty', 1) == 3)
            total_diff = max(1, n1 + n2 + n3)
            # Reserve space on the right for the count label so 2- and 3-digit
            # numbers don't overflow the card border.
            count_label_w = 22
            bar_right = card_rect.right - 16 - count_label_w
            bar_w_max = 90
            bar_h = 7
            bar_gap = 5
            bar_top = card_rect.y + 20
            for i, (count, color) in enumerate([(n1, ACCENT_GREEN), (n2, ACCENT_ORANGE), (n3, ACCENT_RED)]):
                by = bar_top + i * (bar_h + bar_gap)
                pygame.draw.rect(surface, BG_SECONDARY,
                                 (bar_right - bar_w_max, by, bar_w_max, bar_h), border_radius=3)
                fill_w = max(4, int(bar_w_max * count / total_diff))
                pygame.draw.rect(surface, color,
                                 (bar_right - bar_w_max, by, fill_w, bar_h), border_radius=3)
                draw_text(surface, str(count), card_rect.right - 10, by,
                          TEXT_DIM, 11, anchor="topright")

            # Spotlight: radial glow following mouse inside card
            if card_rect.collidepoint(mouse):
                lx = mouse[0] - card_rect.x
                ly = mouse[1] - card_rect.y
                spot_surf = pygame.Surface((card_rect.w, card_rect.h), pygame.SRCALPHA)
                for sr in range(90, 0, -10):
                    a = int(14 * (1 - sr / 90))
                    pygame.draw.circle(spot_surf, (255, 255, 255, a), (lx, ly), sr)
                surface.blit(spot_surf, card_rect.topleft)

            # Dots
            dot_y = card_rect.bottom + 12
            dot_gap = 14
            total_dots = len(self.cert_names)
            dots_w = total_dots * 8 + (total_dots - 1) * (dot_gap - 8)
            dot_x_start = w // 2 - dots_w // 2 + 4
            for i in range(total_dots):
                dx = dot_x_start + i * dot_gap
                if i == self.cert_index:
                    pulse_r = 4 + int(1.5 * abs(math.sin(now * 3.0)))
                    pygame.draw.circle(surface, page_accent, (dx, dot_y), pulse_r)
                else:
                    pygame.draw.circle(surface, BORDER_COLOR, (dx, dot_y), 3)

            # Arrows with page_accent color + smooth hover fade
            self._cert_left_rect, lhov = self._draw_arrow(
                surface, card_x - 40, card_rect.centery, -1, size=16,
                accent_color=page_accent, hover_t=self._cert_left_hover_t, mouse_pos=mouse)
            self._cert_left_hover_t += ((1.0 if lhov else 0.0) - self._cert_left_hover_t) * _lf(0.14, dt)

            self._cert_right_rect, rhov = self._draw_arrow(
                surface, card_x + card_w + 40, card_rect.centery, 1, size=16,
                accent_color=page_accent, hover_t=self._cert_right_hover_t, mouse_pos=mouse)
            self._cert_right_hover_t += ((1.0 if rhov else 0.0) - self._cert_right_hover_t) * _lf(0.14, dt)

            # ── Difficulty Pills ───────────────────────────────────────────
            diff_top = dot_y + 20
            draw_text(surface, "DIFFICULTÉ", w // 2, diff_top, TEXT_DIM, 12,
                      bold=True, anchor="midtop")
            diff_top += 20

            pill_w = 150
            pill_h = 46
            pill_gap = 10
            total_pills_w = 3 * pill_w + 2 * pill_gap
            pill_start_x = w // 2 - total_pills_w // 2

            diff_configs = [
                (1, "Facile", ACCENT_GREEN),
                (2, "Interm.", ACCENT_ORANGE),
                (3, "Difficile", ACCENT_RED),
            ]
            for i, (level, label, color) in enumerate(diff_configs):
                px = pill_start_x + i * (pill_w + pill_gap)
                prect = pygame.Rect(px, diff_top, pill_w, pill_h)
                self._diff_pill_rects[i] = prect
                active = (self.difficulty == level)
                is_hov = prect.collidepoint(mouse) and not active
                self._pill_hover_t[i] += ((1.0 if is_hov else 0.0) - self._pill_hover_t[i]) * _lf(0.14, dt)
                ht = self._pill_hover_t[i]

                if active:
                    draw_glow_rect(surface, prect, color, color, radius=10,
                                   glow_radius=8, glow_alpha=55)
                    draw_text(surface, label, prect.centerx, prect.centery - 7,
                              BG_COLOR, 18, bold=True, anchor="center")
                    draw_text(surface, f"Niveau {level}", prect.centerx, prect.centery + 10,
                              BG_COLOR, 11, anchor="center")
                else:
                    bg_c = _lc(BG_CARD, BG_CARD_HOVER, ht)
                    bc_c = _lc(BORDER_COLOR, color, ht)
                    draw_shadow_rect(surface, prect, bg_c, radius=10, border=1,
                                     border_color=bc_c, shadow_offset=2, shadow_alpha=20)
                    text_c = _lc(TEXT_SECONDARY, color, ht)
                    draw_text(surface, label, prect.centerx, prect.centery - 7,
                              text_c, 18, bold=True, anchor="center")
                    draw_text(surface, f"Niveau {level}", prect.centerx, prect.centery + 10,
                              TEXT_DIM, 11, anchor="center")

            ctrl_top = diff_top + pill_h + 20

        # ── Mode-toggle crossfade overlay ─────────────────────────────────
        # Snapshot the freshly-drawn panel BEFORE applying the fade overlay
        # (so each frame's clean render gets cached for the next transition).
        try:
            snap_rect = pygame.Rect(0, panel_top, w, panel_h_const)
            self._panel_snapshot = surface.subsurface(snap_rect).copy()
            self._panel_snapshot_top = panel_top
        except (ValueError, pygame.error):
            self._panel_snapshot = None

        TRANSITION_DUR = 0.28
        elapsed_t = now - self._transition_start
        if elapsed_t < TRANSITION_DUR and self._transition_fade_snap is not None:
            t_norm = elapsed_t / TRANSITION_DUR
            t_eased = 1.0 - (1.0 - t_norm) ** 3  # ease-out cubic
            alpha = max(0, min(255, int(255 * (1.0 - t_eased))))
            # Use SRCALPHA + BLEND_RGBA_MULT instead of set_alpha — global alpha
            # on RGB surfaces is unreliable on macOS (SDL2/Cocoa).
            snap = self._transition_fade_snap.convert_alpha()
            overlay = pygame.Surface(snap.get_size(), pygame.SRCALPHA)
            overlay.fill((255, 255, 255, alpha))
            snap.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(snap, (0, self._panel_snapshot_top))

        # ── Bottom Controls ────────────────────────────────────────────────
        # Separator
        pygame.draw.line(surface, BORDER_COLOR,
                         (w // 4, ctrl_top), (3 * w // 4, ctrl_top), 1)
        ctrl_top += 18

        # Mode Custom toggle (left of center)
        custom_w = 196
        custom_h = 46
        custom_x = w // 2 - 210
        custom_rect = pygame.Rect(custom_x, ctrl_top, custom_w, custom_h)
        self._custom_rect = custom_rect
        is_hov_custom = custom_rect.collidepoint(mouse)
        self._custom_hover_t += ((1.0 if is_hov_custom else 0.0) - self._custom_hover_t) * _lf(0.14, dt)
        rht = self._custom_hover_t

        if rmt > 0.01:
            draw_glow_rect(surface, custom_rect, page_accent, page_accent,
                           radius=10, glow_radius=6, glow_alpha=int(40 * rmt))
        if rmt < 0.99:
            bg_rv = _lc(BG_CARD, BG_CARD_HOVER, rht)
            bc_rv = _lc(BORDER_COLOR, page_accent, rht)
            alpha_rv = int(255 * (1.0 - rmt))
            overlay = pygame.Surface((custom_rect.w, custom_rect.h), pygame.SRCALPHA)
            draw_shadow_rect(overlay, pygame.Rect(0, 0, custom_rect.w, custom_rect.h),
                             bg_rv, radius=10, border=1, border_color=bc_rv,
                             shadow_offset=2, shadow_alpha=20)
            _amul = pygame.Surface((custom_rect.w, custom_rect.h), pygame.SRCALPHA)
            _amul.fill((255, 255, 255, alpha_rv))
            overlay.blit(_amul, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(overlay, custom_rect.topleft)

        # Toggle switch — knob slides smoothly with rmt
        tog_h = 16
        tog_w = 32
        tog_x = custom_rect.x + 14
        tog_y = custom_rect.centery
        tog_rect = pygame.Rect(tog_x, tog_y - tog_h // 2, tog_w, tog_h)
        tog_bg = _lc(BG_SECONDARY, page_accent, rmt)
        tog_bc = _lc(BORDER_COLOR, page_accent, rmt)
        pygame.draw.rect(surface, tog_bg, tog_rect, border_radius=tog_h // 2)
        pygame.draw.rect(surface, tog_bc, tog_rect, width=1, border_radius=tog_h // 2)
        knob_left = tog_rect.x + tog_h // 2 + 2
        knob_right = tog_rect.right - tog_h // 2 - 2
        knob_x = int(knob_left + (knob_right - knob_left) * rmt)
        knob_color = _lc(TEXT_DIM, TEXT_PRIMARY, rmt)
        pygame.draw.circle(surface, knob_color, (knob_x, tog_y), tog_h // 2 - 2)

        lbl_color = _lc(TEXT_SECONDARY, TEXT_PRIMARY, rmt)
        draw_text(surface, "Mode Custom", tog_rect.right + 10, custom_rect.centery - 6,
                  lbl_color, 15, bold=self.custom_mode, anchor="midleft")
        draw_text(surface, "[C]", tog_rect.right + 10, custom_rect.centery + 10,
                  TEXT_PRIMARY if self.custom_mode else TEXT_DIM, 11, anchor="midleft")

        # Play button (right of center) — fixed position (no gravity/shake)
        play_w = 196
        play_h = 54
        play_x = w // 2 + 14
        play_y = ctrl_top - 4
        play_rect = pygame.Rect(play_x, play_y, play_w, play_h)
        self._play_rect = play_rect
        hover_play = play_rect.collidepoint(mouse)

        is_disabled = not self._can_play()

        if self.custom_mode:
            n_at_diff = len(cert_data.get('all_shortcuts', []))
        else:
            n_at_diff = sum(1 for s in cert_data.get('all_shortcuts', [])
                            if s.get('difficulty', 1) <= self.difficulty)
        pulse = 0.85 + 0.15 * abs(math.sin(now * 2.5))

        if is_disabled:
            # Greyed-out: "Coming Soon" or (custom) "Choisis une certif"
            self._play_hover_t *= 0.86 ** (dt * 60.0)  # fade out
            dim_color = (80, 80, 90)
            draw_glow_rect(surface, play_rect, BG_CARD,
                           dim_color, radius=12, glow_radius=0, glow_alpha=0)
            pygame.draw.rect(surface, dim_color, play_rect, width=2, border_radius=12)
            label = "Coming Soon" if not self.custom_mode else "Choisis une certif"
            draw_text(surface, label, play_rect.centerx, play_rect.centery,
                      dim_color, 18 if self.custom_mode else 22, bold=True, anchor="center")
        else:
            self._play_hover_t += ((1.0 if hover_play else 0.0) - self._play_hover_t) * _lf(0.14, dt)
            pht = self._play_hover_t
            # Design v4: violet → pink gradient body with a soft halo behind it
            col_a = page_accent
            col_b = page_accent2
            # Soft outer halo (not additive — just a falloff surface)
            halo_a = int(60 + pht * 70 + pulse * 14)
            halo_r = 22
            halo = _get_glow_surface(play_rect.w, play_rect.h, col_a,
                                     radius=halo_r, alpha=halo_a)
            surface.blit(halo, (play_rect.x - halo_r, play_rect.y - halo_r))
            # Gradient body
            draw_gradient_rect(surface, play_rect, col_a, col_b,
                               radius=12, direction="horizontal")
            # Hover brighten overlay (masked to the rounded shape)
            if pht > 0.02:
                hov = pygame.Surface((play_rect.w, play_rect.h), pygame.SRCALPHA)
                pygame.draw.rect(hov, (255, 255, 255, int(28 * pht)),
                                 (0, 0, play_rect.w, play_rect.h),
                                 border_radius=12)
                surface.blit(hov, play_rect.topleft)
            draw_text(surface, "JOUER", play_rect.centerx, play_rect.centery - 8,
                      (255, 255, 255), 30, bold=True, anchor="center")
            draw_text(surface, f"{n_at_diff} raccourcis", play_rect.centerx,
                      play_rect.centery + 14, (240, 240, 255), 12, anchor="center")

        # ── Footer ────────────────────────────────────────────────────────
        if self.custom_mode:
            footer_txt = "C: mode custom  |  S: stats  |  L: classement  |  Entrée: jouer  |  Échap: quitter"
        else:
            footer_txt = "Flèches: certif  |  1/2/3: difficulté  |  C: mode custom  |  S: stats  |  L: classement  |  Entrée: jouer  |  Échap: quitter"
        draw_text(surface, footer_txt,
                  w // 2, h - 18, TEXT_DIM, 12, anchor="midbottom")

        # ── Bottom-right quick links ───────────────────────────────────────
        btn_h = 28
        btn_gap = 8
        margin = 14

        # "Choose your vibe" button (rightmost) — two lines
        vibe_w = 160
        vibe_h = 36
        vibe_x = w - margin - vibe_w
        vibe_y = h - margin - vibe_h
        vibe_rect = pygame.Rect(vibe_x, vibe_y, vibe_w, vibe_h)
        self._vibe_rect = vibe_rect
        vibe_color = ACCENT_ORANGE
        self._vibe_hover_t += ((1.0 if vibe_rect.collidepoint(mouse) else 0.0) - self._vibe_hover_t) * _lf(0.14, dt)
        vht = self._vibe_hover_t
        draw_glow_rect(surface, vibe_rect, _lc(BG_CARD, vibe_color, vht),
                       vibe_color, radius=6, glow_radius=6, glow_alpha=int(vht * 45))
        pygame.draw.rect(surface, vibe_color, vibe_rect, width=1, border_radius=6)
        draw_text(surface, "Choose your vibe", vibe_rect.centerx, vibe_rect.centery - 7,
                  _lc(vibe_color, BG_COLOR, vht), 12, bold=True, anchor="center")
        draw_text(surface, "to relax/study to", vibe_rect.centerx, vibe_rect.centery + 8,
                  _lc(TEXT_DIM, BG_COLOR, vht), 10, bold=False, anchor="center")

        # "ALP" button (to the left of vibe)
        alp_w = 46
        alp_x = vibe_x - btn_gap - alp_w
        alp_rect = pygame.Rect(alp_x, vibe_y, alp_w, vibe_h)
        self._alp_rect = alp_rect
        alp_color = ACCENT_BLUE
        self._alp_hover_t += ((1.0 if alp_rect.collidepoint(mouse) else 0.0) - self._alp_hover_t) * _lf(0.14, dt)
        aht = self._alp_hover_t
        draw_glow_rect(surface, alp_rect, _lc(BG_CARD, alp_color, aht),
                       alp_color, radius=6, glow_radius=6, glow_alpha=int(aht * 45))
        pygame.draw.rect(surface, alp_color, alp_rect, width=1, border_radius=6)
        draw_text(surface, "ALP", alp_rect.centerx, alp_rect.centery,
                  _lc(alp_color, BG_COLOR, aht), 12, bold=True, anchor="center")

        # ── Reset button (small link above pseudo field) ──────────────────
        reset_w = 160
        reset_h = 18
        reset_x = margin
        reset_y = vibe_y - reset_h - 6
        reset_btn_rect = pygame.Rect(reset_x, reset_y, reset_w, reset_h)
        self._reset_btn_rect = reset_btn_rect

        if self._reset_confirm:
            draw_text(surface, "Effacer toutes les donnees ?",
                      reset_btn_rect.x, reset_btn_rect.centery,
                      ACCENT_RED, 10, anchor="midleft")
            # [Oui] [Non] inline
            yes_w, no_w = 30, 30
            yes_x = reset_btn_rect.x + 164
            no_x = yes_x + yes_w + 6
            yes_rect = pygame.Rect(yes_x, reset_y, yes_w, reset_h)
            no_rect = pygame.Rect(no_x, reset_y, no_w, reset_h)
            self._reset_yes_rect = yes_rect
            self._reset_no_rect = no_rect

            self._reset_yes_hover_t += ((1.0 if yes_rect.collidepoint(mouse) else 0.0)
                                        - self._reset_yes_hover_t) * _lf(0.14, dt)
            self._reset_no_hover_t += ((1.0 if no_rect.collidepoint(mouse) else 0.0)
                                       - self._reset_no_hover_t) * _lf(0.14, dt)

            pygame.draw.rect(surface, _lc(BORDER_COLOR, ACCENT_RED, self._reset_yes_hover_t),
                             yes_rect, border_radius=3)
            draw_text(surface, "Oui", yes_rect.centerx, yes_rect.centery,
                      TEXT_PRIMARY, 10, bold=True, anchor="center")

            pygame.draw.rect(surface, _lc(BORDER_COLOR, TEXT_SECONDARY, self._reset_no_hover_t),
                             no_rect, border_radius=3)
            draw_text(surface, "Non", no_rect.centerx, no_rect.centery,
                      TEXT_PRIMARY, 10, bold=True, anchor="center")
        else:
            self._reset_yes_rect = None
            self._reset_no_rect = None
            is_hov_reset = reset_btn_rect.collidepoint(mouse)
            self._reset_hover_t += ((1.0 if is_hov_reset else 0.0)
                                    - self._reset_hover_t) * _lf(0.14, dt)
            draw_text(surface, "Effacer les donnees",
                      reset_btn_rect.x, reset_btn_rect.centery,
                      _lc(TEXT_DIM, ACCENT_RED, self._reset_hover_t),
                      10, anchor="midleft")

        # ── Pseudo field (bottom-left, symmetric to ALP/vibe) ─────────────
        pseudo_w = 160
        pseudo_x = margin
        pseudo_rect = pygame.Rect(pseudo_x, vibe_y, pseudo_w, vibe_h)
        self._pseudo_rect = pseudo_rect

        is_hov_pseudo = pseudo_rect.collidepoint(mouse)
        self._pseudo_hover_t += ((1.0 if (is_hov_pseudo or self._pseudo_editing) else 0.0)
                                 - self._pseudo_hover_t) * _lf(0.14, dt)
        pst = self._pseudo_hover_t

        pseudo_color = page_accent if self._pseudo_editing else _lc(BORDER_COLOR, page_accent, pst)
        draw_shadow_rect(surface, pseudo_rect, _lc(BG_CARD, BG_CARD_HOVER, pst),
                         radius=6, border=1, border_color=pseudo_color,
                         shadow_offset=2, shadow_alpha=15)

        if self._pseudo_editing:
            display_text = self._pseudo_input
            cursor_visible = int(time.time() * 2) % 2 == 0
            cursor = "|" if cursor_visible else " "
            draw_text(surface, display_text + cursor,
                      pseudo_rect.x + 10, pseudo_rect.centery,
                      TEXT_PRIMARY, 13, anchor="midleft")
            draw_text(surface, "3-15 car.",
                      pseudo_rect.right - 8, pseudo_rect.y + 4,
                      TEXT_DIM, 9, anchor="topright")
        elif self._pseudo:
            draw_text(surface, self._pseudo,
                      pseudo_rect.centerx, pseudo_rect.centery - 6,
                      _lc(TEXT_SECONDARY, TEXT_PRIMARY, pst), 13,
                      bold=True, anchor="center")
            draw_text(surface, "Pseudo", pseudo_rect.centerx, pseudo_rect.centery + 7,
                      TEXT_DIM, 9, anchor="center")
        else:
            draw_text(surface, "Entrer un pseudo",
                      pseudo_rect.centerx, pseudo_rect.centery,
                      TEXT_DIM, 12, anchor="center")

        # ── Intro fade-in (slow & progressive) ────────────────────────────
        # Whole menu fades up from black over ~3.5s with a soft ease-out so
        # the reveal feels gentle: the curve stays bright early then trails off.
        INTRO_DUR = 3.5
        if age < INTRO_DUR:
            t = age / INTRO_DUR
            t_eased = 1.0 - (1.0 - t) ** 3  # ease-out cubic
            alpha = int(255 * (1.0 - t_eased))
            if alpha > 0:
                fade_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
                fade_overlay.fill((BG_COLOR[0], BG_COLOR[1], BG_COLOR[2], alpha))
                surface.blit(fade_overlay, (0, 0))


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
                 custom_bonus=False, custom_show_answer=False, custom_random=True):
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
        self.flash_color = None
        self.flash_until = 0.0

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
        _DBLCLICK_THRESHOLD = 0.4  # seconds between clicks

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

    def _do_correct(self):
        response_time = max(0.0, time.time() - self._shortcut_shown_at)
        self._record_correct(self.state.current_shortcut)
        points = self.state.on_correct()
        self._score_flash_t = 1.0  # design v4: scoreUp animation
        self._check_achievements_correct(response_time)
        w = pygame.display.get_surface().get_size()[0]
        center_x = (w - 260) // 2
        center_y = 300

        # Score popup
        big = self.state.combo >= 5
        self.popups.append(ScorePopup(
            f"+{points}", center_x + random.randint(-20, 20),
            center_y - 40 + random.randint(-10, 10),
            ACCENT_GREEN if self.state.combo < 5 else ACCENT_GOLD,
            big=big
        ))

        # Particles — explosive!
        combo = self.state.combo
        if combo >= 10:
            color = ACCENT_GOLD
            self.particles.extend(spawn_explosion(center_x, center_y, color, PARTICLES_CORRECT_HIGH))
            self.particles.extend(spawn_sparks(center_x, center_y, (255, 255, 200), 30))
        elif combo >= 5:
            color = ACCENT_GOLD
            self.particles.extend(spawn_explosion(center_x, center_y, color, PARTICLES_CORRECT))
            self.particles.extend(spawn_sparks(center_x, center_y, color, 15))
        else:
            color = ACCENT_GREEN
            self.particles.extend(spawn_explosion(center_x, center_y, color, PARTICLES_CORRECT))

        # Combo milestone fireworks
        if combo in COMBO_MILESTONES and combo > self._prev_combo:
            self.particles.extend(spawn_firework_ring(center_x, center_y, ACCENT_GOLD,
                                                      PARTICLES_MILESTONE))
            self.popups.append(ScorePopup(
                f"COMBO x{combo}!", center_x, center_y - 80, ACCENT_PURPLE, big=True
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

    def _do_wrong(self):
        self.state.on_wrong()
        self._prev_combo = 0
        self._consecutive_correct = 0
        self.flash_color = ACCENT_RED
        self.flash_until = time.time() + 0.25
        self.shake_intensity = max(self.shake_intensity, SHAKE_WRONG)

        w = pygame.display.get_surface().get_size()[0]
        center_x = (w - 260) // 2
        self.popups.append(ScorePopup("RATÉ", center_x, 280, ACCENT_RED))
        self.particles.extend(spawn_wrong_burst(center_x, 300, PARTICLES_WRONG))
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
                                self._do_correct()
                                return None
                            elif result == 'wait':
                                return None  # waiting for second click
                            # 'wrong' falls through to alt check
                        else:
                            if self.kbd.check_modifiers_for_click(exp_mods):
                                self._do_correct()
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
                                self._do_correct()
                                alt_matched = True
                                break
                            elif result == 'wait':
                                alt_matched = True  # don't judge yet
                                break
                        else:
                            if self.kbd.check_modifiers_for_click(alt_mods):
                                self._do_correct()
                                alt_matched = True
                                break
                    if alt_matched:
                        return None
                    self._do_wrong()
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
            keys_small = sc.get(_KEYS_SMALL, sc.get('keys', []))
            keys_big   = sc.get(_KEYS_BIG,   sc.get('keys', []))
            if not IS_MAC:
                if input_type == 'key_sequence':
                    keys_big = _to_azerty_display_seq(keys_big)
                else:
                    keys_big = _to_azerty_display(keys_big)
            fade = self._reveal_fade_t

            if show_answer and fade > 0.02:
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
                # `?` placeholder keycaps
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


# ---------------------------------------------------------------------------
# Stats Screen
# ---------------------------------------------------------------------------

class StatsScreen:
    """Per-certification shortcut statistics screen."""

    _SORT_MODES = [('rate', 'Par taux'), ('views', 'Par vues'), ('name', 'Par nom')]
    _ROW_H = 62
    _HEADER_H = 172  # pixels reserved above the scrollable list

    def __init__(self, certifications, initial_cert=None):
        ordered = [c for c in CERT_ORDER if c in certifications]
        extras = sorted(c for c in certifications if c not in ordered)
        self.cert_names = ordered + extras
        self.certifications = certifications

        if initial_cert and initial_cert in self.cert_names:
            self.cert_index = self.cert_names.index(initial_cert)
        else:
            self.cert_index = 0

        self.cert_name = self.cert_names[self.cert_index]
        self.cert_data = certifications[self.cert_name]
        self.stats = load_stats(self.cert_name)  # {command_name: {views, correct, total_time}}
        self._sort_mode = 'rate'
        self._rows = []          # sorted shortcuts (full list)
        self._display_rows = []  # filtered by search query
        self._scroll_y = 0.0
        self._scroll_target = 0.0
        self._sort_btn_rects = {}
        self._back_rect = None
        self._cert_left_rect = None
        self._cert_right_rect = None
        self._cert_slide_pos = 0.0
        self._cert_slide_target = 0.0
        self._search_query = ''
        self._search_active = False
        self._search_rect = None
        self._build_rows()

    def _change_cert(self, direction):
        self.cert_index = (self.cert_index + direction) % len(self.cert_names)
        self._cert_slide_target = direction * 110
        self.cert_name = self.cert_names[self.cert_index]
        self.cert_data = self.certifications[self.cert_name]
        self.stats = load_stats(self.cert_name)
        self._build_rows()
        self._scroll_target = 0.0

    @staticmethod
    def _fmt_keys(sc, field='keys_win'):
        """Format a shortcut's keys as a compact string, including alternatives."""
        keys = sc.get(field, [])
        if not keys:
            return ''
        input_type = sc.get('input_type', 'key_combo')

        def _fmt_one(k, itype):
            if itype == 'key_sequence':
                parts = ['+'.join(step) if isinstance(step, list) else str(step)
                         for step in k]
                return '  >  '.join(parts)
            if isinstance(k, list) and all(isinstance(x, str) for x in k):
                # Replace Click/Right-Click with French labels
                display = []
                for key in k:
                    if key == 'Click':
                        display.append('clic')
                    elif key == 'Double-Click':
                        display.append('double-clic')
                    elif key == 'Right-Click':
                        display.append('clic droit')
                    else:
                        display.append(key)
                return '+'.join(display)
            return ''

        result = _fmt_one(keys, input_type)
        for alt in sc.get('alt', []):
            alt_keys = alt.get(field, alt.get('keys_win', []))
            alt_type = alt.get('input_type', input_type)
            alt_str = _fmt_one(alt_keys, alt_type)
            if alt_str:
                result += ' / ' + alt_str
        return result

    def _draw_arrow(self, surface, cx, cy, direction, mouse):
        size = 14
        rect = pygame.Rect(cx - size - 8, cy - size - 8, (size + 8) * 2, (size + 8) * 2)
        hov = rect.collidepoint(mouse)
        color = _lc(ACCENT_BLUE, (255, 255, 255), 0.3 if hov else 0.0)
        if direction == -1:
            pts = [(cx + size // 2, cy - size), (cx - size // 2, cy), (cx + size // 2, cy + size)]
        else:
            pts = [(cx - size // 2, cy - size), (cx + size // 2, cy), (cx - size // 2, cy + size)]
        pygame.draw.polygon(surface, color, pts)
        return rect

    def _build_rows(self):
        """Build and sort the row list according to current sort mode."""
        all_sc = self.cert_data.get('all_shortcuts', [])

        def _entry(sc):
            return self.stats.get(sc.get('command_name', ''),
                                  {'views': 0, 'correct': 0, 'total_time': 0.0})

        def _rate(sc):
            e = _entry(sc)
            if e['views'] == 0:
                return -1.0  # unseen → bottom in rate sort
            return e['correct'] / e['views']

        if self._sort_mode == 'rate':
            self._rows = sorted(all_sc, key=_rate)   # worst first
        elif self._sort_mode == 'views':
            self._rows = sorted(all_sc, key=lambda s: _entry(s)['views'], reverse=True)
        else:
            self._rows = sorted(all_sc, key=lambda s: s.get('command_name', '').lower())
        self._apply_filter()

    def _apply_filter(self):
        """Recompute _display_rows from _rows + current search query."""
        q = self._search_query.lower().strip()
        if not q:
            self._display_rows = self._rows
        else:
            self._display_rows = [
                sc for sc in self._rows
                if (q in (sc.get('command_name') or '').lower() or
                    q in (sc.get('context') or '').lower() or
                    q in (sc.get('category') or '').lower() or
                    q in self._fmt_keys(sc, 'keys_win').lower() or
                    q in self._fmt_keys(sc, 'keys_mac').lower())
            ]
        self._scroll_target = 0.0

    def _clamp_scroll(self, h):
        viewport_h = h - self._HEADER_H - 20
        total_h = len(self._display_rows) * self._ROW_H
        max_scroll = max(0, total_h - viewport_h)
        self._scroll_target = max(0.0, min(float(max_scroll), self._scroll_target))

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if self._search_active:
                if event.key == pygame.K_ESCAPE:
                    if self._search_query:
                        self._search_query = ''
                        self._apply_filter()
                    else:
                        self._search_active = False
                elif event.key == pygame.K_BACKSPACE:
                    self._search_query = self._search_query[:-1]
                    self._apply_filter()
                elif event.unicode and event.unicode.isprintable():
                    self._search_query += event.unicode
                    self._apply_filter()
                return None  # consume all keys when search is focused
            else:
                if event.key == pygame.K_ESCAPE:
                    return 'menu'
                if event.key == pygame.K_DOWN:
                    self._scroll_target += self._ROW_H * 3
                if event.key == pygame.K_UP:
                    self._scroll_target -= self._ROW_H * 3
                if event.key == pygame.K_LEFT:
                    self._change_cert(-1)
                if event.key == pygame.K_RIGHT:
                    self._change_cert(1)

        if event.type == pygame.MOUSEWHEEL:
            self._scroll_target -= event.y * self._ROW_H * 3

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            # Toggle search focus on click
            if self._search_rect and self._search_rect.collidepoint(pos):
                self._search_active = True
                return None
            self._search_active = False

            if self._back_rect and self._back_rect.collidepoint(pos):
                return 'menu'
            if self._cert_left_rect and self._cert_left_rect.collidepoint(pos):
                self._change_cert(-1)
            elif self._cert_right_rect and self._cert_right_rect.collidepoint(pos):
                self._change_cert(1)
            else:
                for mode, rect in self._sort_btn_rects.items():
                    if rect.collidepoint(pos):
                        self._sort_mode = mode
                        self._build_rows()
                        break
        return None

    def draw(self, surface, dt=0.016):
        w, h = surface.get_size()
        surface.fill(BG_COLOR)

        # Smooth scroll
        self._clamp_scroll(h)
        self._scroll_y += (self._scroll_target - self._scroll_y) * _lf(0.25, dt)

        # ── Header ────────────────────────────────────────────────────────
        mouse = pygame.mouse.get_pos()

        # Title (left) + Back button (right)
        draw_text(surface, "Stats", 24, 32, ACCENT_BLUE, 26, bold=True, anchor="midleft")

        back_rect = pygame.Rect(w - 120, 18, 106, 30)
        self._back_rect = back_rect
        back_hov = back_rect.collidepoint(mouse)
        pygame.draw.rect(surface, _lc(BG_CARD, BORDER_COLOR, 0.6 if back_hov else 0.0),
                         back_rect, border_radius=6)
        pygame.draw.rect(surface, BORDER_COLOR, back_rect, width=1, border_radius=6)
        draw_text(surface, "Echap  Retour", back_rect.centerx, back_rect.centery,
                  TEXT_SECONDARY, 12, anchor="center")

        # Cert carousel (centered)
        self._cert_slide_pos += (self._cert_slide_target - self._cert_slide_pos) * _lf(0.25, dt)
        self._cert_slide_target *= 0.70 ** (dt * 60.0)

        cx = w // 2
        cert_slide_x = cx + int(self._cert_slide_pos)
        draw_text(surface, "CERTIFICATION", cx, 36, TEXT_DIM, 10, bold=True, anchor="midtop")
        draw_text(surface, self.cert_name, cert_slide_x, 52,
                  TEXT_PRIMARY, 20, bold=True, anchor="midtop")

        arr_y = 62
        self._cert_left_rect  = self._draw_arrow(surface, cx - 120, arr_y, -1, mouse)
        self._cert_right_rect = self._draw_arrow(surface, cx + 120, arr_y,  1, mouse)

        # Cert index dots
        if len(self.cert_names) > 1:
            dot_total = len(self.cert_names) * 10
            dot_x = cx - dot_total // 2
            for i in range(len(self.cert_names)):
                col = ACCENT_BLUE if i == self.cert_index else BORDER_COLOR
                r = 3 if i == self.cert_index else 2
                pygame.draw.circle(surface, col, (dot_x + i * 10 + 4, 80), r)

        # Summary row
        all_sc = self.cert_data.get('all_shortcuts', [])
        total = len(all_sc)
        seen = sum(1 for s in all_sc
                   if self.stats.get(s.get('command_name', ''), {}).get('views', 0) > 0)
        total_views = sum(e.get('views', 0) for e in self.stats.values())
        total_correct = sum(e.get('correct', 0) for e in self.stats.values())
        global_rate = int(total_correct / total_views * 100) if total_views > 0 else 0
        filtered_count = len(self._display_rows)
        if self._search_query and filtered_count != total:
            summary = (f"{filtered_count}/{total} raccourcis   "
                       f"Taux global: {global_rate}%   "
                       f"Reponses: {total_correct}/{total_views}")
        else:
            summary = (f"{total} raccourcis   {seen} vus   "
                       f"Taux global: {global_rate}%   "
                       f"Reponses: {total_correct}/{total_views}")
        draw_text(surface, summary, 24, 90, TEXT_SECONDARY, 12, anchor="midleft")

        # Sort buttons
        sort_x = 24
        sort_y = 108
        btn_w, btn_h = 110, 26
        self._sort_btn_rects = {}
        for mode, label in self._SORT_MODES:
            active = (mode == self._sort_mode)
            rect = pygame.Rect(sort_x, sort_y, btn_w, btn_h)
            self._sort_btn_rects[mode] = rect
            bg = _lc(BG_CARD, ACCENT_BLUE, 0.4 if active else 0.0)
            border = ACCENT_BLUE if active else BORDER_COLOR
            pygame.draw.rect(surface, bg, rect, border_radius=6)
            pygame.draw.rect(surface, border, rect, width=1, border_radius=6)
            draw_text(surface, label, rect.centerx, rect.centery,
                      TEXT_PRIMARY if active else TEXT_DIM, 12,
                      bold=active, anchor="center")
            sort_x += btn_w + 8

        # Search bar (right side of sort buttons row)
        sb_w = 220
        sb_rect = pygame.Rect(w - sb_w - 16, sort_y, sb_w, btn_h)
        self._search_rect = sb_rect
        sb_active = self._search_active
        sb_border = ACCENT_BLUE if sb_active else BORDER_COLOR
        sb_bg = _lc(BG_COLOR, BG_CARD, 0.9 if sb_active else 0.4)
        pygame.draw.rect(surface, sb_bg, sb_rect, border_radius=6)
        pygame.draw.rect(surface, sb_border, sb_rect, width=1, border_radius=6)

        # Magnifier icon (circle + handle drawn with primitives)
        ic_cx, ic_cy, ic_r = sb_rect.x + 14, sb_rect.centery, 5
        pygame.draw.circle(surface, TEXT_DIM, (ic_cx, ic_cy), ic_r, 1)
        pygame.draw.line(surface, TEXT_DIM,
                         (ic_cx + ic_r - 1, ic_cy + ic_r - 1),
                         (ic_cx + ic_r + 3, ic_cy + ic_r + 3), 1)

        # Query text or placeholder
        font_s = get_font(11, False)
        text_x = sb_rect.x + 26
        max_text_w = sb_w - 34 - (10 if sb_active else 0)
        if self._search_query:
            # Show tail of query if too long
            q_display = self._search_query
            while q_display and font_s.size(q_display)[0] > max_text_w:
                q_display = q_display[1:]
            q_surf = font_s.render(q_display, True, TEXT_PRIMARY)
            surface.blit(q_surf, (text_x, sb_rect.centery - q_surf.get_height() // 2))
            # Clear button (×) when query is non-empty
            clr_x = sb_rect.right - 14
            draw_text(surface, 'x', clr_x, sb_rect.centery, TEXT_DIM, 10, anchor="center")
        else:
            ph_surf = font_s.render('Rechercher...', True, TEXT_DIM)
            surface.blit(ph_surf, (text_x, sb_rect.centery - ph_surf.get_height() // 2))

        # Blinking cursor
        if sb_active and time.time() % 1.0 < 0.6:
            q_w = font_s.size(self._search_query)[0] if self._search_query else 0
            # clamp to available width
            q_w = min(q_w, max_text_w)
            cur_x = text_x + q_w + 1
            pygame.draw.line(surface, TEXT_PRIMARY,
                             (cur_x, sb_rect.y + 5), (cur_x, sb_rect.bottom - 5), 1)

        # Column headers
        header_y = 154
        col_x = self._col_positions(w)
        pygame.draw.line(surface, BORDER_COLOR, (16, header_y - 8), (w - 16, header_y - 8))
        draw_text(surface, "COMMANDE / CATEGORIE / RACCOURCIS", col_x['name'], header_y,
                  TEXT_DIM, 11, bold=True, anchor="midleft")
        draw_text(surface, "VUS", col_x['views'], header_y,
                  TEXT_DIM, 11, bold=True, anchor="midright")
        draw_text(surface, "TAUX", col_x['rate'], header_y,
                  TEXT_DIM, 11, bold=True, anchor="midleft")
        draw_text(surface, "TEMPS MOY.", col_x['time'], header_y,
                  TEXT_DIM, 11, bold=True, anchor="midright")
        pygame.draw.line(surface, BORDER_COLOR, (16, header_y + 12), (w - 16, header_y + 12))

        # ── Scrollable rows ───────────────────────────────────────────────
        list_top = self._HEADER_H
        viewport_h = h - list_top - 20
        clip_rect = pygame.Rect(0, list_top, w, viewport_h)
        old_clip = surface.get_clip()
        surface.set_clip(clip_rect)

        scroll_int = int(self._scroll_y)
        for i, sc in enumerate(self._display_rows):
            row_y = list_top + i * self._ROW_H - scroll_int
            if row_y + self._ROW_H < list_top:
                continue
            if row_y > list_top + viewport_h:
                break
            self._draw_row(surface, sc, row_y, w, mouse, col_x)

        # Empty state when search yields no results
        if not self._display_rows and self._search_query:
            draw_text(surface, f'Aucun raccourci pour "{self._search_query}"',
                      w // 2, list_top + 60, TEXT_DIM, 14, anchor="center")

        surface.set_clip(old_clip)

        # Scroll indicator
        if len(self._display_rows) * self._ROW_H > viewport_h:
            total_h = len(self._display_rows) * self._ROW_H
            bar_h = max(30, int(viewport_h * viewport_h / total_h))
            bar_y = list_top + int(self._scroll_y / max(1, total_h - viewport_h)
                                   * (viewport_h - bar_h))
            pygame.draw.rect(surface, BORDER_COLOR,
                             pygame.Rect(w - 6, bar_y, 4, bar_h), border_radius=2)

        draw_vignette(surface, 0.15)

    def _col_positions(self, w):
        return {
            'name':  24,
            'views': w - 270,
            'rate':  w - 240,
            'time':  w - 30,
        }

    def _draw_row(self, surface, sc, row_y, w, mouse, col_x):
        key = sc.get('command_name', '')
        entry = self.stats.get(key, {'views': 0, 'correct': 0, 'total_time': 0.0})
        views = entry.get('views', 0)
        correct = entry.get('correct', 0)
        total_time = entry.get('total_time', 0.0)

        # Row hover background
        row_rect = pygame.Rect(8, row_y, w - 16, self._ROW_H - 2)
        if row_rect.collidepoint(mouse):
            pygame.draw.rect(surface, BG_CARD, row_rect, border_radius=4)

        # Command name
        name = key if key else sc.get('command_name', '?')
        draw_text(surface, name, col_x['name'], row_y + 10,
                  TEXT_PRIMARY, 13, bold=True, anchor="midleft")

        # Context (truncated to fit column width)
        ctx = sc.get('context') or ''
        if ctx:
            font_ctx = get_font(10, False)
            max_w = col_x['views'] - col_x['name'] - 20
            while ctx and font_ctx.size(ctx)[0] > max_w:
                ctx = ctx[:-1]
            if ctx != sc.get('context', ''):
                ctx = ctx.rstrip() + '...'
            draw_text(surface, ctx, col_x['name'], row_y + 23,
                      TEXT_DIM, 10, anchor="midleft")

        # Category (small, dimmer, below context)
        cat = sc.get('category', '')
        if cat:
            draw_text(surface, cat, col_x['name'], row_y + 35,
                      (60, 65, 85), 9, anchor="midleft")

        # Shortcut keys (Win and Mac notations)
        win_txt = self._fmt_keys(sc, 'keys_win')
        mac_txt = self._fmt_keys(sc, 'keys_mac')
        font_k = get_font(10, False)
        kx = col_x['name']
        key_y = row_y + 50
        if win_txt:
            win_col = ACCENT_BLUE if not IS_MAC else TEXT_DIM
            s = font_k.render(win_txt, True, win_col)
            surface.blit(s, (kx, key_y - s.get_height() // 2))
            kx += s.get_width()
        if win_txt and mac_txt:
            sep = font_k.render('  ·  ', True, TEXT_DIM)
            surface.blit(sep, (kx, key_y - sep.get_height() // 2))
            kx += sep.get_width()
        if mac_txt:
            mac_col = ACCENT_GREEN if IS_MAC else TEXT_DIM
            s = font_k.render(mac_txt, True, mac_col)
            surface.blit(s, (kx, key_y - s.get_height() // 2))

        # Stats columns — vertically centered in the row
        stat_y = row_y + 31

        # Views count
        views_col = TEXT_DIM if views == 0 else TEXT_SECONDARY
        draw_text(surface, str(views) if views > 0 else '-',
                  col_x['views'], stat_y, views_col, 12, anchor="midright")

        # Rate bar + percentage
        bar_x = col_x['rate']
        bar_y = row_y + 27
        bar_w = 100
        bar_h = 8
        if views > 0:
            rate = correct / views
            pct = int(rate * 100)
            if rate >= 0.8:
                bar_color = ACCENT_GREEN
            elif rate >= 0.5:
                bar_color = ACCENT_ORANGE
            else:
                bar_color = ACCENT_RED
            pygame.draw.rect(surface, _lc(BG_CARD, bar_color, 0.3),
                             pygame.Rect(bar_x, bar_y, bar_w, bar_h), border_radius=3)
            fill_w = int(bar_w * rate)
            if fill_w > 0:
                pygame.draw.rect(surface, bar_color,
                                 pygame.Rect(bar_x, bar_y, fill_w, bar_h), border_radius=3)
            draw_text(surface, f"{pct}%", bar_x + bar_w + 8, stat_y,
                      bar_color, 11, anchor="midleft")
        else:
            draw_text(surface, '-', bar_x + bar_w // 2, stat_y,
                      TEXT_DIM, 11, anchor="center")

        # Avg time
        if correct > 0:
            avg = total_time / correct
            draw_text(surface, f"{avg:.1f}s", col_x['time'], stat_y,
                      TEXT_SECONDARY, 12, anchor="midright")
        else:
            draw_text(surface, '-', col_x['time'], stat_y,
                      TEXT_DIM, 12, anchor="midright")


# ---------------------------------------------------------------------------
# Leaderboard Screen
# ---------------------------------------------------------------------------

class LeaderboardScreen:
    """Local + global high-score screen, filterable by cert × difficulty."""

    def __init__(self, certifications, initial_cert=None):
        from game.leaderboard import (load_local_highscores, fetch_online_scores_async,
                                      load_config)
        self.certifications = certifications
        ordered = [c for c in CERT_ORDER if c in certifications]
        extras = sorted(c for c in certifications if c not in ordered)
        self.cert_names = ordered + extras

        self.cert_index = self.cert_names.index(initial_cert) if initial_cert in self.cert_names else 0
        self.difficulty = 1

        self._local_hs = load_local_highscores()
        self._online_scores = []          # fetched async
        self._online_loading = False
        self._online_error = False
        self._has_supabase = load_config() is not None

        self._back_rect = None
        self._diff_rects = [None, None, None]
        self._cert_left_rect = None
        self._cert_right_rect = None
        self._cert_slide_pos = 0.0
        self._cert_slide_target = 0.0
        self._refresh_rect = None

        self._fetch_online()

    def _fetch_online(self):
        if not self._has_supabase:
            return
        from game.leaderboard import fetch_online_scores_async
        self._online_loading = True
        self._online_error = False
        self._online_scores = []

        def _done(results):
            self._online_scores = results
            self._online_loading = False
            if results == [] and self._has_supabase:
                self._online_error = True

        fetch_online_scores_async(self.cert_names[self.cert_index],
                                  self.difficulty, _done)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return 'menu'
            if event.key == pygame.K_LEFT:
                self.cert_index = (self.cert_index - 1) % len(self.cert_names)
                self._cert_slide_target = -110
                self._fetch_online()
            if event.key == pygame.K_RIGHT:
                self.cert_index = (self.cert_index + 1) % len(self.cert_names)
                self._cert_slide_target = 110
                self._fetch_online()
            if event.key == pygame.K_1:
                self.difficulty = 1; self._fetch_online()
            if event.key == pygame.K_2:
                self.difficulty = 2; self._fetch_online()
            if event.key == pygame.K_3:
                self.difficulty = 3; self._fetch_online()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self._back_rect and self._back_rect.collidepoint(pos):
                return 'menu'
            if self._cert_left_rect and self._cert_left_rect.collidepoint(pos):
                self.cert_index = (self.cert_index - 1) % len(self.cert_names)
                self._cert_slide_target = -110
                self._fetch_online()
            elif self._cert_right_rect and self._cert_right_rect.collidepoint(pos):
                self.cert_index = (self.cert_index + 1) % len(self.cert_names)
                self._cert_slide_target = 110
                self._fetch_online()
            elif self._refresh_rect and self._refresh_rect.collidepoint(pos):
                self._fetch_online()
            else:
                for i, r in enumerate(self._diff_rects):
                    if r and r.collidepoint(pos):
                        self.difficulty = i + 1
                        self._fetch_online()
                        break
        return None

    def draw(self, surface, dt=0.016):
        w, h = surface.get_size()
        surface.fill(BG_COLOR)
        mouse = pygame.mouse.get_pos()

        # Cert slide
        self._cert_slide_pos += (self._cert_slide_target - self._cert_slide_pos) * _lf(0.25, dt)
        self._cert_slide_target *= 0.70 ** (dt * 60.0)

        cert_name = self.cert_names[self.cert_index]

        # ── Header ────────────────────────────────────────────────────────
        draw_text(surface, "Classement", 24, 28, ACCENT_GOLD, 28, bold=True, anchor="midleft")

        back_rect = pygame.Rect(w - 120, 14, 106, 30)
        self._back_rect = back_rect
        pygame.draw.rect(surface, BG_CARD, back_rect, border_radius=6)
        pygame.draw.rect(surface, BORDER_COLOR, back_rect, width=1, border_radius=6)
        draw_text(surface, "Echap  Retour", back_rect.centerx, back_rect.centery,
                  TEXT_SECONDARY, 12, anchor="center")

        # Cert carousel
        cx = w // 2
        cert_x = cx + int(self._cert_slide_pos)
        draw_text(surface, "CERTIFICATION", cx, 65, TEXT_DIM, 11, bold=True, anchor="midtop")
        draw_text(surface, cert_name, cert_x, 82, TEXT_PRIMARY, 22, bold=True, anchor="midtop")

        arr_y = 93
        lrect, _ = self._draw_arrow(surface, cx - 120, arr_y, -1, page_accent=ACCENT_GOLD, mouse=mouse)
        rrect, _ = self._draw_arrow(surface, cx + 120, arr_y, 1, page_accent=ACCENT_GOLD, mouse=mouse)
        self._cert_left_rect = lrect
        self._cert_right_rect = rrect

        # Difficulty pills
        pill_labels = ['Facile', 'Interm.', 'Difficile']
        pill_colors = [ACCENT_GREEN, ACCENT_ORANGE, ACCENT_RED]
        pill_w, pill_h, pill_gap = 100, 28, 8
        pill_total = 3 * pill_w + 2 * pill_gap
        pill_x = cx - pill_total // 2
        pill_y = 118
        self._diff_rects = []
        for i, (lbl, col) in enumerate(zip(pill_labels, pill_colors)):
            rect = pygame.Rect(pill_x, pill_y, pill_w, pill_h)
            self._diff_rects.append(rect)
            active = (self.difficulty == i + 1)
            bg = _lc(BG_CARD, col, 0.4 if active else 0.0)
            border = col if active else BORDER_COLOR
            pygame.draw.rect(surface, bg, rect, border_radius=6)
            pygame.draw.rect(surface, border, rect, width=1, border_radius=6)
            draw_text(surface, lbl, rect.centerx, rect.centery,
                      TEXT_PRIMARY if active else TEXT_DIM, 12, bold=active, anchor="center")
            pill_x += pill_w + pill_gap

        pygame.draw.line(surface, BORDER_COLOR, (16, 158), (w - 16, 158))

        # ── Two-column layout ─────────────────────────────────────────────
        col_gap = 16
        col_w = (w - 48) // 2   # 16px left margin + gap + 16px right
        local_x = 16
        online_x = local_x + col_w + col_gap
        list_y = 168

        # Local column
        draw_text(surface, "Meilleur score local", local_x, list_y,
                  ACCENT_BLUE, 14, bold=True, anchor="midleft")
        self._draw_local_column(surface, local_x, list_y + 24, col_w, cert_name)

        # Online column
        if self._has_supabase:
            online_title = "Top 10 mondial"
            draw_text(surface, online_title, online_x, list_y,
                      ACCENT_PURPLE, 14, bold=True, anchor="midleft")

            # Refresh button
            ref_rect = pygame.Rect(online_x + col_w - 70, list_y - 8, 66, 22)
            self._refresh_rect = ref_rect
            pygame.draw.rect(surface, BG_CARD, ref_rect, border_radius=4)
            pygame.draw.rect(surface, BORDER_COLOR, ref_rect, width=1, border_radius=4)
            draw_text(surface, "Actualiser", ref_rect.centerx, ref_rect.centery,
                      TEXT_DIM, 10, anchor="center")

            self._draw_online_column(surface, online_x, list_y + 24, col_w)
        else:
            draw_text(surface, "Top mondial (non configure)", online_x, list_y,
                      TEXT_DIM, 14, bold=True, anchor="midleft")
            draw_text(surface, "Creer supabase_config.json",
                      online_x, list_y + 30, TEXT_DIM, 12, anchor="midleft")
            draw_text(surface, "avec url et anon_key Supabase.",
                      online_x, list_y + 48, TEXT_DIM, 12, anchor="midleft")
            self._refresh_rect = None

        draw_vignette(surface, 0.15)

    def _draw_arrow(self, surface, cx, cy, direction, page_accent, mouse):
        size = 14
        rect = pygame.Rect(cx - size - 8, cy - size - 8, (size + 8) * 2, (size + 8) * 2)
        hov = rect.collidepoint(mouse)
        color = _lc(page_accent, (255, 255, 255), 0.3 if hov else 0.0)
        if direction == -1:
            pts = [(cx + size // 2, cy - size), (cx - size // 2, cy), (cx + size // 2, cy + size)]
        else:
            pts = [(cx - size // 2, cy - size), (cx + size // 2, cy), (cx - size // 2, cy + size)]
        pygame.draw.polygon(surface, color, pts)
        return rect, hov

    def _draw_local_column(self, surface, x, y, col_w, cert_name):
        from game.leaderboard import _hs_key
        diff_labels = {1: 'Facile', 2: 'Interm.', 3: 'Difficile'}
        diff_colors = {1: ACCENT_GREEN, 2: ACCENT_ORANGE, 3: ACCENT_RED}

        for diff in [1, 2, 3]:
            key = _hs_key(cert_name, diff)
            entry = self._local_hs.get(key)
            label = diff_labels[diff]
            col = diff_colors[diff]

            row_rect = pygame.Rect(x, y, col_w, 52)
            pygame.draw.rect(surface, BG_CARD, row_rect, border_radius=6)
            pygame.draw.rect(surface, _lc(BORDER_COLOR, col, 0.3 if diff == self.difficulty else 0.0),
                             row_rect, width=1, border_radius=6)

            draw_text(surface, label, x + 12, y + 10, col, 11, bold=True, anchor="midleft")
            if entry:
                draw_text(surface, str(entry['score']), x + 12, y + 30,
                          TEXT_PRIMARY, 20, bold=True, anchor="midleft")
                draw_text(surface, entry.get('pseudo', '?'), x + col_w - 12, y + 14,
                          TEXT_SECONDARY, 12, anchor="midright")
                draw_text(surface, entry.get('date', ''), x + col_w - 12, y + 30,
                          TEXT_DIM, 10, anchor="midright")
            else:
                draw_text(surface, '-', x + 12, y + 30, TEXT_DIM, 18, anchor="midleft")
            y += 58

    def _draw_online_column(self, surface, x, y, col_w):
        if self._online_loading:
            draw_text(surface, "Chargement...", x, y + 20, TEXT_DIM, 13, anchor="midleft")
            return
        if not self._online_scores:
            draw_text(surface, "Aucun score en ligne.", x, y + 20, TEXT_DIM, 13, anchor="midleft")
            draw_text(surface, "(verifiez la connexion / config)", x, y + 38,
                      TEXT_DIM, 11, anchor="midleft")
            return

        row_h = 28
        for i, entry in enumerate(self._online_scores[:10]):
            ry = y + i * row_h
            rank_color = (ACCENT_GOLD if i == 0 else
                          TEXT_SECONDARY if i == 1 else
                          _lc(TEXT_DIM, TEXT_SECONDARY, 0.5))
            draw_text(surface, f"#{i + 1}", x, ry + 14, rank_color, 12,
                      bold=(i < 3), anchor="midleft")
            pseudo = entry.get('pseudo', '?')
            score = entry.get('score', 0)
            draw_text(surface, pseudo, x + 30, ry + 14, TEXT_PRIMARY, 13, anchor="midleft")
            draw_text(surface, str(score), x + col_w - 8, ry + 14,
                      ACCENT_GOLD if i == 0 else TEXT_SECONDARY, 13,
                      bold=(i == 0), anchor="midright")
