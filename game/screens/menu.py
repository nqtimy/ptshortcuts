"""MenuScreen — certification selection, carousel navigation, and custom mode."""
import math
import random
import time
import webbrowser

import pygame

from game.config import *
from game.screens._shared import _lc, _lf, CERT_ORDER, COMING_SOON, DIFFICULTY_LABELS
from game.renderer import (
    draw_border_glow, draw_button, draw_combo_text, draw_flash, draw_glow_rect,
    draw_key_combo, draw_key_sequence, draw_particles, draw_rounded_rect,
    draw_score_popups, draw_shadow_rect, draw_text, draw_text_glow,
    draw_timer_bar, draw_vignette, get_font,
    draw_text_gradient, draw_gradient_rect, draw_radial_halo, draw_padlock,
    draw_progress_bar, draw_corner_frame,
    ease_out_cubic, lerp_color, lerp_color_stops, frame_lerp,
    _get_glow_surface, _scale_alpha,
)
from game.state import (load_pseudo, save_pseudo, reset_all_data,
                        load_setting, save_setting)


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

        # "Sans pavé numérique" toggle (filter shortcuts unplayable w/o numpad)
        self.no_numpad = bool(load_setting('_no_numpad', False))
        self._numpad_btn_rect = None
        self._numpad_hover_t = 0.0

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
            elif self._numpad_btn_rect and self._numpad_btn_rect.collidepoint(pos):
                self.no_numpad = not self.no_numpad
                save_setting('_no_numpad', self.no_numpad)
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

        # ── "Sans pavé num." toggle (above the reset link) ────────────────
        np_w = 160
        np_h = 16
        np_x = margin
        np_y = vibe_y - 18 - 6 - np_h - 4
        np_rect = pygame.Rect(np_x, np_y, np_w, np_h)
        self._numpad_btn_rect = np_rect
        is_hov_np = np_rect.collidepoint(mouse)
        self._numpad_hover_t += ((1.0 if is_hov_np else 0.0)
                                 - self._numpad_hover_t) * _lf(0.14, dt)
        # Small square indicator + label
        box_sz = 10
        box_y = np_rect.centery - box_sz // 2
        box_rect = pygame.Rect(np_x, box_y, box_sz, box_sz)
        box_col = page_accent if self.no_numpad else _lc(BORDER_COLOR, page_accent,
                                                          self._numpad_hover_t)
        pygame.draw.rect(surface, box_col, box_rect, width=1, border_radius=2)
        if self.no_numpad:
            inner = box_rect.inflate(-4, -4)
            pygame.draw.rect(surface, page_accent, inner, border_radius=1)
        label_col = _lc(TEXT_DIM, TEXT_SECONDARY,
                        max(self._numpad_hover_t,
                            1.0 if self.no_numpad else 0.0))
        draw_text(surface, "Sans pavé numérique",
                  np_x + box_sz + 8, np_rect.centery,
                  label_col, 10, anchor="midleft")

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
