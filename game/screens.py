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
        self.cert_index = 0
        self.difficulty = 1  # 1, 2 or 3
        self.review_mode = False
        self.timer_enabled = True
        self.selected = None
        self.selected_difficulty = None
        self.selected_review = False
        self.selected_timer = True
        self.show_stats = False
        self.show_leaderboard = False
        self.birth = time.time()

        # Animations
        self._waveform_phases = [random.uniform(0, math.pi * 2) for _ in range(40)]
        self._waveform_speeds = [random.uniform(1.8, 4.0) for _ in range(40)]
        self._bg_particles = []   # [x, y, vx, vy, alpha_scale, color_idx]
        self._particle_layer = None
        self._play_gravity = [0.0, 0.0]
        self._review_mode_t = 0.0  # 0.0 = normal (blue), 1.0 = review mode (red)
        self._cert_slide_pos = 0.0     # actual rendered x offset (never jumps)
        self._cert_slide_target = 0.0  # target x offset (can jump on press)
        self._cert_left_hover_t = 0.0
        self._cert_right_hover_t = 0.0
        # Hover fade interpolation values (0.0 = idle, 1.0 = fully hovered)
        self._pill_hover_t = [0.0, 0.0, 0.0]
        self._review_hover_t = 0.0
        self._play_hover_t = 0.0
        self._alp_hover_t = 0.0
        self._vibe_hover_t = 0.0
        self._timer_hover_t = 0.0
        self._timer_rect = None

        # Button rects for hit-testing
        self._cert_left_rect = None
        self._cert_right_rect = None
        self._diff_pill_rects = [None, None, None]
        self._play_rect = None
        self._review_rect = None
        self._alp_rect = None
        self._vibe_rect = None
        self._pseudo_rect = None

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

            if self._cert_left_rect and self._cert_left_rect.collidepoint(pos):
                self.cert_index = (self.cert_index - 1) % len(self.cert_names)
                self._cert_slide_target = -110
            elif self._cert_right_rect and self._cert_right_rect.collidepoint(pos):
                self.cert_index = (self.cert_index + 1) % len(self.cert_names)
                self._cert_slide_target = 110
            elif self._review_rect and self._review_rect.collidepoint(pos):
                self.review_mode = not self.review_mode
            elif self._timer_rect and self._timer_rect.collidepoint(pos):
                self.timer_enabled = not self.timer_enabled
            elif self._play_rect and self._play_rect.collidepoint(pos) and self.current_cert not in COMING_SOON:
                self.selected = self.current_cert
                self.selected_difficulty = self.difficulty
                self.selected_review = self.review_mode
                self.selected_timer = self.timer_enabled if self.review_mode else True
            elif self._alp_rect and self._alp_rect.collidepoint(pos):
                webbrowser.open("https://alp.avidlearningcentral.com/users/sign_in")
            elif self._vibe_rect and self._vibe_rect.collidepoint(pos):
                webbrowser.open("https://www.youtube.com/playlist?list=PL6NdkXsPL07Il2hEQGcLI4dg_LTg7xA2L")
            else:
                for i, prect in enumerate(self._diff_pill_rects):
                    if prect and prect.collidepoint(pos):
                        self.difficulty = i + 1
                        break

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                self.cert_index = (self.cert_index - 1) % len(self.cert_names)
                self._cert_slide_target = -110
            elif event.key == pygame.K_RIGHT:
                self.cert_index = (self.cert_index + 1) % len(self.cert_names)
                self._cert_slide_target = 110
            elif event.key == pygame.K_UP:
                self.difficulty = min(3, self.difficulty + 1)
            elif event.key == pygame.K_DOWN:
                self.difficulty = max(1, self.difficulty - 1)
            elif event.key == pygame.K_1:
                self.difficulty = 1
            elif event.key == pygame.K_2:
                self.difficulty = 2
            elif event.key == pygame.K_3:
                self.difficulty = 3
            elif event.key == pygame.K_r:
                self.review_mode = not self.review_mode
            elif event.key == pygame.K_s:
                self.show_stats = True
            elif event.key == pygame.K_l:
                self.show_leaderboard = True
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.current_cert not in COMING_SOON:
                    self.selected = self.current_cert
                    self.selected_difficulty = self.difficulty
                    self.selected_review = self.review_mode

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
        self._review_mode_t += ((1.0 if self.review_mode else 0.0) - self._review_mode_t) * _lf(0.05, dt)
        rmt = self._review_mode_t
        page_accent = _lc(ACCENT_BLUE, ACCENT_RED, rmt)
        page_accent2 = _lc(ACCENT_PURPLE, ACCENT_ORANGE, rmt)
        surface.fill(BG_COLOR)

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
        draw_text_glow(surface, "PT Shortcuts", w // 2, title_y, page_accent,
                       size=58, bold=True, anchor="midtop", glow_alpha=45)
        draw_text(surface, "Pro Tools Keyboard Trainer", w // 2, title_y + 68,
                  TEXT_SECONDARY, 20, anchor="midtop")

        # ── Animated waveform separator ───────────────────────────────────
        sep_y = title_y + 110
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

        # ── Certification Carousel ─────────────────────────────────────────
        cert_name = self.current_cert
        cert_data = self.certifications[cert_name]

        carousel_top = sep_y + 24
        draw_text(surface, "CERTIFICATION", w // 2, carousel_top, TEXT_DIM, 12,
                  bold=True, anchor="midtop")
        carousel_top += 20

        card_w = min(480, w - 160)
        card_h = 120
        card_x = (w - card_w) // 2
        card_rect = pygame.Rect(card_x, carousel_top, card_w, card_h)

        # Entrance animation (vertical)
        slide = max(0, 20 * (1.0 - min(1.0, age / 0.4)))
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

        # Left accent bar
        accent_rect = pygame.Rect(card_rect.x + 1, card_rect.y + 14, 4, card_rect.h - 28)
        pygame.draw.rect(surface, page_accent, accent_rect, border_radius=2)

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
        bar_right = card_rect.right - 16
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
            draw_text(surface, str(count), bar_right + 6, by, TEXT_DIM, 11, anchor="topleft")

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

        # ── Difficulty Pills ───────────────────────────────────────────────
        diff_top = dot_y + 20
        draw_text(surface, "DIFFICULTE", w // 2, diff_top, TEXT_DIM, 12,
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

        # ── Bottom Controls ────────────────────────────────────────────────
        ctrl_top = diff_top + pill_h + 20
        # Separator
        pygame.draw.line(surface, BORDER_COLOR,
                         (w // 4, ctrl_top), (3 * w // 4, ctrl_top), 1)
        ctrl_top += 18

        # Review toggle (left of center)
        review_w = 196
        review_h = 46
        review_x = w // 2 - 210
        review_rect = pygame.Rect(review_x, ctrl_top, review_w, review_h)
        self._review_rect = review_rect
        is_hov_review = review_rect.collidepoint(mouse)
        self._review_hover_t += ((1.0 if is_hov_review else 0.0) - self._review_hover_t) * _lf(0.14, dt)
        rht = self._review_hover_t

        if rmt > 0.01:
            draw_glow_rect(surface, review_rect, page_accent, page_accent,
                           radius=10, glow_radius=6, glow_alpha=int(40 * rmt))
        if rmt < 0.99:
            bg_rv = _lc(BG_CARD, BG_CARD_HOVER, rht)
            bc_rv = _lc(BORDER_COLOR, page_accent, rht)
            alpha_rv = int(255 * (1.0 - rmt))
            overlay = pygame.Surface((review_rect.w, review_rect.h), pygame.SRCALPHA)
            draw_shadow_rect(overlay, pygame.Rect(0, 0, review_rect.w, review_rect.h),
                             bg_rv, radius=10, border=1, border_color=bc_rv,
                             shadow_offset=2, shadow_alpha=20)
            overlay.set_alpha(alpha_rv)
            surface.blit(overlay, review_rect.topleft)

        # Toggle switch — knob slides smoothly with rmt
        tog_h = 16
        tog_w = 32
        tog_x = review_rect.x + 14
        tog_y = review_rect.centery
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
        draw_text(surface, "Mode Revision", tog_rect.right + 10, review_rect.centery - 6,
                  lbl_color, 15, bold=self.review_mode, anchor="midleft")
        draw_text(surface, "[R]", tog_rect.right + 10, review_rect.centery + 10,
                  ACCENT_PURPLE if self.review_mode else TEXT_DIM, 11, anchor="midleft")

        # Timer toggle — only visible in review mode (fades with rmt)
        if rmt > 0.02:
            timer_w = review_w
            timer_h = 30
            timer_x = review_x
            timer_y_pos = review_rect.bottom + 6
            timer_rect = pygame.Rect(timer_x, timer_y_pos, timer_w, timer_h)
            self._timer_rect = timer_rect if rmt > 0.4 else None  # disable clicks when fading

            self._timer_hover_t += ((1.0 if timer_rect.collidepoint(mouse) and rmt > 0.4 else 0.0)
                                    - self._timer_hover_t) * _lf(0.14, dt)
            tht = self._timer_hover_t

            timer_color = page_accent if self.timer_enabled else TEXT_DIM
            bg_t = _lc(BG_CARD, BG_CARD_HOVER, tht)
            bc_t = _lc(BORDER_COLOR, timer_color, max(tht, 0.4 if self.timer_enabled else 0.0))
            draw_shadow_rect(surface, timer_rect, bg_t, radius=8, border=1,
                             border_color=bc_t, shadow_offset=2, shadow_alpha=15)

            # Mini toggle knob
            knob_h = 12
            knob_rect = pygame.Rect(timer_rect.x + 10, timer_rect.centery - knob_h // 2, 24, knob_h)
            knob_bg = _lc(BG_SECONDARY, timer_color, 1.0 if self.timer_enabled else 0.0)
            pygame.draw.rect(surface, knob_bg, knob_rect, border_radius=knob_h // 2)
            kx = knob_rect.right - knob_h // 2 - 1 if self.timer_enabled else knob_rect.x + knob_h // 2 + 1
            pygame.draw.circle(surface, TEXT_PRIMARY if self.timer_enabled else TEXT_DIM,
                               (kx, timer_rect.centery), knob_h // 2 - 1)

            label = "Timer actif" if self.timer_enabled else "Sans timer"
            draw_text(surface, label, knob_rect.right + 8, timer_rect.centery,
                      _lc(TEXT_DIM, timer_color, 1.0 if self.timer_enabled else 0.0),
                      13, anchor="midleft")

            # Apply global alpha for fade in/out
            if rmt < 0.95:
                fade = pygame.Surface((timer_w, timer_h), pygame.SRCALPHA)
                fade.fill((0, 0, 0, int((1.0 - rmt) * 255)))
                surface.blit(fade, timer_rect.topleft)
        else:
            self._timer_rect = None

        # Play button (right of center) — magnetic gravity toward mouse
        play_w = 196
        play_h = 54
        base_play_cx = w // 2 + 14 + play_w // 2
        base_play_cy = ctrl_top - 4 + play_h // 2
        dist_x = mouse[0] - base_play_cx
        dist_y = mouse[1] - base_play_cy
        dist = math.sqrt(dist_x ** 2 + dist_y ** 2)
        if dist < 120 and dist > 0:
            strength = (1 - dist / 120) ** 2 * 9
            target_gx = dist_x / dist * strength
            target_gy = dist_y / dist * strength
        else:
            target_gx, target_gy = 0.0, 0.0
        self._play_gravity[0] += (target_gx - self._play_gravity[0]) * _lf(0.18, dt)
        self._play_gravity[1] += (target_gy - self._play_gravity[1]) * _lf(0.18, dt)
        play_x = w // 2 + 14 + int(self._play_gravity[0])
        play_y = ctrl_top - 4 + int(self._play_gravity[1])
        play_rect = pygame.Rect(play_x, play_y, play_w, play_h)
        self._play_rect = play_rect
        hover_play = play_rect.collidepoint(mouse)

        is_coming_soon = self.current_cert in COMING_SOON

        n_at_diff = sum(1 for s in cert_data.get('all_shortcuts', [])
                        if s.get('difficulty', 1) <= self.difficulty)
        pulse = 0.85 + 0.15 * abs(math.sin(now * 2.5))

        if is_coming_soon:
            # Greyed-out button with "Coming Soon"
            self._play_hover_t *= 0.86 ** (dt * 60.0)  # fade out
            dim_color = (80, 80, 90)
            draw_glow_rect(surface, play_rect, BG_CARD,
                           dim_color, radius=12, glow_radius=0, glow_alpha=0)
            pygame.draw.rect(surface, dim_color, play_rect, width=2, border_radius=12)
            draw_text(surface, "Coming Soon", play_rect.centerx, play_rect.centery,
                      dim_color, 22, bold=True, anchor="center")
        else:
            self._play_hover_t += ((1.0 if hover_play else 0.0) - self._play_hover_t) * _lf(0.14, dt)
            pht = self._play_hover_t
            play_color = _lc(ACCENT_GREEN, page_accent, rmt)
            pulse_color = (int(play_color[0] * pulse), int(play_color[1] * pulse),
                           int(play_color[2] * pulse))
            glow_a = int(pht * 80)
            draw_glow_rect(surface, play_rect, _lc(BG_CARD, pulse_color, pht),
                           play_color, radius=12, glow_radius=16, glow_alpha=glow_a)
            pygame.draw.rect(surface, pulse_color, play_rect, width=2, border_radius=12)
            draw_text(surface, "JOUER", play_rect.centerx, play_rect.centery - 8,
                      _lc(play_color, BG_COLOR, pht), 28, bold=True, anchor="center")
            draw_text(surface, f"{n_at_diff} raccourcis", play_rect.centerx,
                      play_rect.centery + 14, TEXT_DIM, 12, anchor="center")

        # ── Footer ────────────────────────────────────────────────────────
        draw_text(surface,
                  "Fleches: certif  |  1/2/3: difficulte  |  R: revision  |  S: stats  |  L: classement  |  Entree: jouer  |  Echap: quitter",
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


# ---------------------------------------------------------------------------
# Game Screen
# ---------------------------------------------------------------------------

class GameScreen:
    """Main gameplay screen with explosive effects."""

    def __init__(self, cert_name, cert_data, kbd_handler, max_difficulty=3, review_mode=False, timer_enabled=True):
        self.cert_name = cert_name
        self.cert_data = cert_data
        self.kbd = kbd_handler
        self.max_difficulty = max_difficulty
        self.review_mode = review_mode
        self.timer_enabled = timer_enabled

        # Init state
        self.state = GameState(cert_name, cert_data['category_names'])
        saved = load_game()
        if cert_name in saved:
            self.state.load_from_dict(saved[cert_name])
        self.state.total_score = 0
        self.state.spent_score = 0

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
        self.upgrade_rects = {}
        self.cat_unlock_rect = None
        self.back_rect = None
        self.hovered_upgrade = None
        self.action_rects = {}

        # Game over
        self.game_over = False
        self.game_over_time = 0.0
        self.game_over_restart_rect = None
        self.game_over_menu_rect = None
        self.game_over_answer = None

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
        self._review_playlist = []
        self._review_index = 0
        if self.review_mode:
            self._build_review_playlist()

        self._next_shortcut()

    def _build_review_playlist(self):
        """Build a shuffled list of all shortcuts at the selected difficulty."""
        all_sc = self.cert_data.get('all_shortcuts', [])
        self._review_playlist = [s for s in all_sc
                                 if s.get('difficulty', 1) <= self.max_difficulty]
        random.shuffle(self._review_playlist)
        self._review_index = 0

    def _next_shortcut(self):
        if self.review_mode:
            if not self._review_playlist:
                return
            # Loop: reshuffle when we've gone through all
            if self._review_index >= len(self._review_playlist):
                random.shuffle(self._review_playlist)
                self._review_index = 0
            chosen = self._review_playlist[self._review_index]
            self._review_index += 1
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

    def _check_alt_combo(self, sc):
        """Check alternative shortcuts. Returns True if any alt matches (and triggers correct)."""
        for alt_det in sc.get('_detect_alt', []):
            alt_type = alt_det.get('_detect_input_type', 'key_combo')
            alt_opts = alt_det.get('_detect_key_options', [])
            if not alt_opts:
                continue
            if alt_type == 'single_key':
                first_opt = next(iter(alt_opts[0])) if alt_opts else ''
                if first_opt in ('Win', 'Ctrl', 'Shift', 'Alt'):
                    if self.kbd.check_modifier_only(alt_det.get('_detect_modifiers')) is True:
                        self._do_correct()
                        return True
                else:
                    if self.kbd.check_combo_v2(alt_opts) is True:
                        self._do_correct()
                        return True
            elif alt_type == 'key_combo':
                if self.kbd.check_combo_v2(alt_opts) is True:
                    self._do_correct()
                    return True
        return False

    def _do_correct(self):
        response_time = max(0.0, time.time() - self._shortcut_shown_at)
        self._record_correct(self.state.current_shortcut)
        points = self.state.on_correct()
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
        self.popups.append(ScorePopup("RATE", center_x, 280, ACCENT_RED))
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
        saved = load_game()
        if not self.review_mode:
            saved[self.cert_name] = self.state.to_dict()
        # Always persist stats (review mode included)
        if '_stats' not in saved:
            saved['_stats'] = {}
        saved['_stats'][self.cert_name] = self._stats_cache
        save_game(saved)

        # High-score check (only non-review sessions with actual score)
        if not self.review_mode and self.state.total_score > 0:
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

                if not self.review_mode:
                    for uid, rect in self.upgrade_rects.items():
                        if rect.collidepoint(pos):
                            if self.state.buy_upgrade(uid):
                                self._unlock_achievement('upgrade_1')
                                if uid == 'skip':
                                    self.state.use_skip()
                                    self._next_shortcut()
                                elif uid == 'freeze':
                                    self.state.use_freeze()
                            return None

                    if self.cat_unlock_rect and self.cat_unlock_rect.collidepoint(pos):
                        if self.state.unlock_next_category():
                            self._unlock_achievement('cat_unlock')
                        return None

                    for action, rect in self.action_rects.items():
                        if rect.collidepoint(pos):
                            if action == 'skip' and self.state.use_skip():
                                self._next_shortcut()
                            elif action == 'reveal':
                                self.state.use_reveal()
                                self._unlock_achievement('reveal_1')
                            elif action == 'freeze':
                                self.state.use_freeze()
                            elif action == 'double':
                                self.state.use_double()
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
                        result = self.kbd.check_combo_v2(detect_opts)
                        if result is True:
                            self._do_correct()
                        elif result is False:
                            if not self._check_alt_combo(sc):
                                self._do_wrong()
                else:
                    result = self.kbd.check_combo_v2(detect_opts)
                    if result is True:
                        self._do_correct()
                    elif result is False:
                        if not self._check_alt_combo(sc):
                            self._do_wrong()

            if self.state.current_shortcut:
                if self.state.is_frozen():
                    self.state.timer_start += dt
                elif not self.timer_enabled:
                    self.state.timer_start = now  # timer never expires
                elif self.review_mode:
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

    def get_shake_offset(self):
        return self.shake_x, self.shake_y

    def draw(self, surface):
        w, h = surface.get_size()
        surface.fill(BG_COLOR)
        now = time.time()

        if self.review_mode:
            panel_w = 0
        else:
            panel_w = min(280, max(200, w // 5))
        game_area_w = w - panel_w
        game_cx = game_area_w // 2

        # Vignette
        draw_vignette(surface, 0.2)

        # Right panel (hidden in review mode)
        if not self.review_mode:
            self._draw_panel(surface, w, h, panel_w)

        # Back button
        self.back_rect = draw_button(surface, "< Menu", (12, 12, 100, 36),
                                     text_size=15, border_color=BORDER_COLOR)

        # Review mode banner
        if self.review_mode:
            total = len(self._review_playlist)
            current = min(self._review_index, total)
            banner_text = f"REVISION  {current} / {total}"
            banner_w = 200
            banner_h = 28
            banner_rect = pygame.Rect(game_cx - banner_w // 2, 12, banner_w, banner_h)
            draw_glow_rect(surface, banner_rect, BG_CARD, ACCENT_PURPLE,
                           radius=8, glow_radius=6, glow_alpha=35)
            draw_text(surface, banner_text, game_cx, banner_rect.centery,
                      ACCENT_PURPLE, 14, bold=True, anchor="center")

        # Score with glow
        score_text = f"{self.state.available_score}"
        if not self.review_mode:
            draw_text(surface, "SCORE", game_cx, 12, TEXT_DIM, 13, bold=True, anchor="midtop")
            draw_text_glow(surface, score_text, game_cx, 32, ACCENT_GOLD, size=34,
                           bold=True, anchor="midtop", glow_alpha=30)

        # Level and stats
        stats_y = 46 if self.review_mode else 68
        draw_text(surface, f"Niveau {self.state.level}", game_cx, stats_y,
                  TEXT_SECONDARY, 15, anchor="midtop")
        stats_text = f"Réussis: {self.state.total_correct}  |  Ratés: {self.state.total_wrong}"
        draw_text(surface, stats_text, game_cx, stats_y + 18, TEXT_DIM, 13, anchor="midtop")

        # Combo
        draw_combo_text(surface, self.state.combo, game_cx, stats_y + 50)

        # Active effects
        if not self.review_mode:
            effects_y = 148
            if self.state.is_frozen():
                remaining = self.state.freeze_until - now
                draw_text_glow(surface, f"FREEZE {remaining:.1f}s", game_cx, effects_y,
                               ACCENT_BLUE, size=18, bold=True, anchor="midtop", glow_alpha=50)
                effects_y += 24
            if self.state.is_double():
                remaining = self.state.double_until - now
                draw_text_glow(surface, f"x2 POINTS {remaining:.1f}s", game_cx, effects_y,
                               ACCENT_PURPLE, size=18, bold=True, anchor="midtop", glow_alpha=50)

        # Current shortcut
        sc = self.state.current_shortcut
        if sc:
            cat = sc.get('category', '')
            draw_text(surface, cat.upper(), game_cx, 180, TEXT_DIM, 13,
                      bold=True, anchor="midtop")

            # Difficulty dots
            diff = sc.get('difficulty', 1)
            diff_colors = {1: ACCENT_GREEN, 2: ACCENT_ORANGE, 3: ACCENT_RED}
            dot_color = diff_colors.get(diff, TEXT_PRIMARY)
            dot_y = 200
            dot_r = 5
            dot_gap = 14
            total_dot_w = 3 * dot_r * 2 + 2 * dot_gap
            dot_x = game_cx - total_dot_w // 2 + dot_r
            for i in range(3):
                if i < diff:
                    pygame.draw.circle(surface, dot_color, (dot_x, dot_y), dot_r)
                    # Glow on filled dots
                    glow_s = pygame.Surface((dot_r * 6, dot_r * 6), pygame.SRCALPHA)
                    pygame.draw.circle(glow_s, (*dot_color, 40),
                                       (dot_r * 3, dot_r * 3), dot_r * 3)
                    surface.blit(glow_s, (dot_x - dot_r * 3, dot_y - dot_r * 3))
                else:
                    pygame.draw.circle(surface, BORDER_COLOR, (dot_x, dot_y), dot_r, 1)
                dot_x += dot_r * 2 + dot_gap

            # Command name — big, with shadow
            cmd_name = sc.get('command_name', '???')
            cmd_size = min(48, max(30, 48 - len(cmd_name) // 3))
            draw_text(surface, cmd_name, game_cx, 225, TEXT_PRIMARY, cmd_size,
                      bold=True, anchor="midtop", max_width=game_area_w - 60, shadow=True)

            # Context banner
            context = sc.get('context')
            context_y = 290
            if context:
                ctx_text = f"[i] {context}"
                ctx_font = get_font(14, False)
                banner_w = min(game_area_w - 80, 700)
                text_max = banner_w - 24
                # Check if text fits on one line
                rendered = ctx_font.render(ctx_text, True, ACCENT_ORANGE)
                if rendered.get_width() <= text_max:
                    banner_h = 34
                    banner_x = game_cx - banner_w // 2
                    draw_shadow_rect(surface, (banner_x, context_y, banner_w, banner_h),
                                     BG_CONTEXT, radius=8, shadow_offset=2, shadow_alpha=40)
                    draw_text(surface, ctx_text, game_cx, context_y + banner_h // 2,
                              ACCENT_ORANGE, 14, anchor="center")
                else:
                    # Word-wrap into two lines
                    words = ctx_text.split()
                    line1 = ""
                    for i, w in enumerate(words):
                        test = (line1 + " " + w).strip()
                        if ctx_font.render(test, True, ACCENT_ORANGE).get_width() > text_max:
                            break
                        line1 = test
                    else:
                        i = len(words)
                    line2 = " ".join(words[i:])
                    banner_h = 50
                    banner_x = game_cx - banner_w // 2
                    draw_shadow_rect(surface, (banner_x, context_y, banner_w, banner_h),
                                     BG_CONTEXT, radius=8, shadow_offset=2, shadow_alpha=40)
                    draw_text(surface, line1, game_cx, context_y + banner_h // 2 - 9,
                              ACCENT_ORANGE, 14, anchor="center")
                    draw_text(surface, line2, game_cx, context_y + banner_h // 2 + 9,
                              ACCENT_ORANGE, 14, anchor="center", max_width=text_max)
                context_y += banner_h + 12

            # Input type hint
            input_type = sc.get('input_type', 'key_combo')
            if input_type == 'key_sequence':
                steps = sc.get('keys_win', [])
                n_steps = len(steps) if isinstance(steps, list) and steps and isinstance(steps[0], list) else 0
                hint_text = f"Sequence ({self._seq_step}/{n_steps})"
                draw_text(surface, hint_text, game_cx, context_y + 4,
                          ACCENT_BLUE, 13, anchor="midtop")
                context_y += 20
            elif input_type == 'modifier_click':
                sc = self.state.current_shortcut
                is_dbl = sc and sc.get('_detect_click') == 'double'
                hint_text = "Maintenez les touches + Double-clic" if is_dbl \
                    else "Maintenez les touches + Clic souris"
                draw_text(surface, hint_text, game_cx, context_y + 4,
                          ACCENT_BLUE, 13, anchor="midtop")
                context_y += 20
            elif input_type == 'single_key':
                hint_text = "Touche seule"
                draw_text(surface, hint_text, game_cx, context_y + 4,
                          TEXT_DIM, 13, anchor="midtop")
                context_y += 20

            # Timer bar
            timer_y = context_y + 15
            if self.timer_enabled:
                elapsed = now - self.state.timer_start
                ratio = max(0.0, 1.0 - elapsed / self.state.timer_duration)
                bar_w = min(420, game_area_w - 100)
                draw_timer_bar(surface, game_cx - bar_w // 2, timer_y, bar_w, 16, ratio,
                               frozen=self.state.is_frozen())
                # Border glow when timer critical
                if ratio < 0.25 and not self.state.is_frozen() and not self.game_over:
                    pulse = abs(math.sin(now * 6))
                    draw_border_glow(surface, ACCENT_RED, pulse * 0.6)
            else:
                ratio = 1.0  # for reveal_y positioning below

            # Revealed answer (always visible in review mode)
            if self.review_mode or self.state.revealed:
                keys_mac = sc.get('keys_mac', sc.get('keys', []))
                keys_win = sc.get('keys_win', sc.get('keys', []))
                input_type = sc.get('input_type', 'key_combo')

                reveal_y = timer_y + 35

                keys_small = sc.get(_KEYS_SMALL, sc.get('keys', []))
                keys_big   = sc.get(_KEYS_BIG,   sc.get('keys', []))

                if input_type == 'key_sequence':
                    # Small (secondary) sequence
                    draw_text(surface, f"{_LABEL_SMALL} :", game_cx, reveal_y,
                              TEXT_DIM, 12, bold=True, anchor="midtop")
                    draw_key_sequence(surface, keys_small, game_cx, reveal_y + 34,
                                      size=26, current_step=len(keys_small), show_all=True)

                    # Big (primary) sequence
                    reveal_y += 64
                    draw_text(surface, f"{_LABEL_BIG} :", game_cx, reveal_y,
                              _COLOR_BIG, 15, bold=True, anchor="midtop")
                    draw_key_sequence(surface, keys_big, game_cx, reveal_y + 44,
                                      size=36, current_step=len(keys_big), show_all=True)
                    reveal_y += 68
                    draw_text(surface, "(Sequence de touches)", game_cx, reveal_y,
                              TEXT_DIM, 13, anchor="midtop")
                else:
                    # Small (secondary) shortcut
                    draw_text(surface, f"{_LABEL_SMALL} :", game_cx, reveal_y,
                              TEXT_DIM, 12, bold=True, anchor="midtop")
                    draw_key_combo(surface, keys_small, game_cx, reveal_y + 34, size=26)

                    # Big (primary) shortcut
                    reveal_y += 64
                    draw_text(surface, f"{_LABEL_BIG} :", game_cx, reveal_y,
                              _COLOR_BIG, 15, bold=True, anchor="midtop")
                    draw_key_combo(surface, keys_big, game_cx, reveal_y + 44)

                    # Input type indicator
                    if input_type == 'modifier_click':
                        reveal_y += 68
                        is_dbl = sc and sc.get('_detect_click') == 'double'
                        _click_label = "(Modificateurs + Double-clic)" if is_dbl \
                            else "(Modificateurs + Clic souris)"
                        draw_text(surface, _click_label, game_cx, reveal_y,
                                  TEXT_DIM, 13, anchor="midtop")
                    elif input_type == 'single_key':
                        reveal_y += 68
                        draw_text(surface, "(Touche seule)", game_cx, reveal_y,
                                  TEXT_DIM, 13, anchor="midtop")

                # Display alternative shortcuts
                for alt in sc.get('alt', []):
                    reveal_y += 24
                    draw_text(surface, "ou", game_cx, reveal_y,
                              TEXT_DIM, 12, anchor="midtop")
                    reveal_y += 18
                    alt_small = alt.get(_KEYS_SMALL, alt.get('keys_win', []))
                    alt_big   = alt.get(_KEYS_BIG,   alt.get('keys_win', []))
                    draw_key_combo(surface, alt_small, game_cx - 100, reveal_y + 14, size=20)
                    draw_key_combo(surface, alt_big, game_cx + 100, reveal_y + 14, size=24)
                    reveal_y += 28

            # Visual keyboard (always visible)
            kb_margin = 40
            kb_w = game_area_w - kb_margin * 2
            kb_row_h = 23  # key_h(20) + gap(3)
            kb_total_h = len(_KB_ROWS) * kb_row_h - 3  # 5 rows
            kb_bottom = (h - 56) if not self.review_mode else (h - 22)
            kb_y = kb_bottom - kb_total_h
            kb_x = kb_margin

            pressed_keys = self.kbd.get_current_keys()
            expected_keys = self._get_expected_keys() if self.review_mode else frozenset()
            self._draw_keyboard(surface, kb_x, kb_y, kb_w, pressed_keys, expected_keys)

        # Action buttons (hidden in review mode)
        if not self.review_mode:
            self._draw_action_buttons(surface, game_cx, h)

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

        # Box slides in from top
        box_w = min(520, w - 80)
        box_h = 480
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

            # Display alternative shortcuts in game over
            for alt in self.game_over_answer.get('alt', []):
                draw_text(surface, "ou", cx, y, TEXT_DIM, 11, anchor="midtop")
                y += 16
                alt_small = alt.get(_KEYS_SMALL, alt.get('keys_win', []))
                alt_big   = alt.get(_KEYS_BIG,   alt.get('keys_win', []))
                draw_key_combo(surface, alt_small, cx - 80, y + 10, size=18)
                draw_key_combo(surface, alt_big, cx + 80, y + 10, size=22)
                y += 30

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

        # Restart
        restart_rect = pygame.Rect(bx, by, btn_w, btn_h)
        self.game_over_restart_rect = restart_rect
        hover_r = restart_rect.collidepoint(mouse)
        if hover_r:
            draw_glow_rect(surface, restart_rect, ACCENT_GREEN, ACCENT_GREEN,
                           radius=10, glow_radius=10, glow_alpha=60)
        else:
            draw_shadow_rect(surface, restart_rect, BG_CARD, radius=10, border=2,
                             border_color=ACCENT_GREEN)
        draw_text(surface, "Recommencer", restart_rect.centerx, restart_rect.centery,
                  BG_COLOR if hover_r else ACCENT_GREEN, 20, bold=True, anchor="center")

        # Menu
        menu_rect = pygame.Rect(bx + btn_w + gap, by, btn_w, btn_h)
        self.game_over_menu_rect = menu_rect
        hover_m = menu_rect.collidepoint(mouse)
        if hover_m:
            draw_glow_rect(surface, menu_rect, ACCENT_BLUE, ACCENT_BLUE,
                           radius=10, glow_radius=10, glow_alpha=60)
        else:
            draw_shadow_rect(surface, menu_rect, BG_CARD, radius=10, border=2,
                             border_color=ACCENT_BLUE)
        draw_text(surface, "Menu", menu_rect.centerx, menu_rect.centery,
                  BG_COLOR if hover_m else ACCENT_BLUE, 20, bold=True, anchor="center")

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
        tag_surf = get_font(9, True).render("SUCCES", True, tag_col[:3])
        tag_surf.set_alpha(alpha)
        notif_surf.blit(tag_surf, (12, 8))

        name_surf = get_font(14, True).render(info['name'], True, name_col[:3])
        name_surf.set_alpha(alpha)
        notif_surf.blit(name_surf, (12, 20))

        desc_surf = get_font(11, False).render(info['desc'], True, desc_col[:3])
        desc_surf.set_alpha(alpha)
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

    def _draw_keyboard(self, surface, kb_x, kb_y, kb_w, highlight_keys, expected_keys):
        """Draw the visual QWERTY Mac keyboard.

        highlight_keys: set of internal names currently pressed (player input) → blue
        expected_keys:  set of internal names for the correct shortcut → green (review only)
        Both pressed and expected → purple.
        """
        gap = 3
        key_h = 20
        row_h = key_h + gap

        unit_px = (kb_w - (_KB_TOTAL_UNITS - 1) * gap) / _KB_TOTAL_UNITS

        for row_i, row in enumerate(_KB_ROWS):
            # Center each row independently (minor width variations)
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
                    bg = _lc(BG_CARD, ACCENT_PURPLE, 0.7)
                    border = ACCENT_PURPLE
                    text_col = TEXT_PRIMARY
                elif pressed:
                    bg = _lc(BG_CARD, ACCENT_BLUE, 0.6)
                    border = ACCENT_BLUE
                    text_col = TEXT_PRIMARY
                elif expected:
                    bg = _lc(BG_CARD, ACCENT_GREEN, 0.35)
                    border = _lc(BORDER_COLOR, ACCENT_GREEN, 0.6)
                    text_col = _lc(TEXT_DIM, ACCENT_GREEN, 0.7)
                else:
                    bg = BG_CARD
                    border = BORDER_COLOR
                    text_col = TEXT_DIM

                pygame.draw.rect(surface, bg, krect, border_radius=3)
                pygame.draw.rect(surface, border, krect, width=1, border_radius=3)

                # Label — smaller font for wide-label keys
                lbl_size = 8 if len(label) > 3 else 9
                draw_text(surface, label, krect.centerx, krect.centery,
                          text_col, lbl_size, anchor="center")

                rx += kw + gap

    def _draw_panel(self, surface, w, h, panel_w):
        px = w - panel_w

        # Panel background with subtle gradient feel
        panel_rect = pygame.Rect(px, 0, panel_w, h)
        pygame.draw.rect(surface, BG_PANEL, panel_rect)
        # Left edge highlight
        pygame.draw.line(surface, BORDER_COLOR, (px, 0), (px, h), 1)

        # Title
        draw_text(surface, "UPGRADES", px + panel_w // 2, 14, TEXT_SECONDARY, 16,
                  bold=True, anchor="midtop")
        # Points
        draw_text_glow(surface, f"{self.state.available_score} pts",
                       px + panel_w // 2, 35, ACCENT_GOLD, size=18, bold=True,
                       anchor="midtop", glow_alpha=20)

        # Upgrade buttons
        y = 62
        self.upgrade_rects = {}
        for uid, udata in UPGRADES.items():
            cost = self.state.upgrade_costs[uid]
            count = self.state.upgrade_counts[uid]
            can_buy = self.state.available_score >= cost
            hovered = self.hovered_upgrade == uid

            btn_rect = pygame.Rect(px + 10, y, panel_w - 20, 62)
            self.upgrade_rects[uid] = btn_rect

            if hovered and can_buy:
                draw_glow_rect(surface, btn_rect, BG_CARD_HOVER, ACCENT_BLUE,
                               radius=10, glow_radius=6, glow_alpha=40)
            elif can_buy:
                draw_shadow_rect(surface, btn_rect, BG_CARD, radius=10, border=1,
                                 border_color=BORDER_COLOR, shadow_offset=2, shadow_alpha=30)
            else:
                draw_rounded_rect(surface, btn_rect, BG_CARD_LOCKED, radius=10, border=1,
                                  border_color=BORDER_COLOR)

            text_col = TEXT_PRIMARY if can_buy else TEXT_DIM
            draw_text(surface, udata['icon'], px + 20, y + 8,
                      ACCENT_BLUE if can_buy else TEXT_DIM, 18, bold=True)
            draw_text(surface, udata['name'], px + 48, y + 8, text_col, 16, bold=True)
            if count > 0:
                draw_text(surface, f"x{count}", px + panel_w - 20, y + 8,
                          ACCENT_GREEN, 14, bold=True, anchor="topright")

            cost_col = ACCENT_GOLD if can_buy else TEXT_DIM
            draw_text(surface, f"{cost} pts", px + 20, y + 32, cost_col, 12)
            draw_text(surface, udata['description'], px + 20, y + 47, TEXT_DIM, 11,
                      max_width=panel_w - 40)
            y += 72

        # Category unlock
        y += 8
        next_cost = self.state.next_category_unlock_cost()
        if next_cost is not None:
            next_idx = len(self.state.unlocked_categories)
            next_cat = self.state.all_categories[next_idx] if next_idx < len(self.state.all_categories) else "?"
            can_unlock = self.state.available_score >= next_cost

            btn_rect = pygame.Rect(px + 10, y, panel_w - 20, 50)
            self.cat_unlock_rect = btn_rect
            if can_unlock:
                draw_shadow_rect(surface, btn_rect, BG_CARD, radius=10, border=1,
                                 border_color=ACCENT_PURPLE, shadow_offset=2, shadow_alpha=30)
            else:
                draw_rounded_rect(surface, btn_rect, BG_CARD_LOCKED, radius=10, border=1,
                                  border_color=BORDER_COLOR)
            text_col = TEXT_PRIMARY if can_unlock else TEXT_DIM
            draw_text(surface, f"Débloquer : {next_cat}", px + 20, y + 8, text_col, 14,
                      bold=True, max_width=panel_w - 40)
            draw_text(surface, f"{next_cost} pts", px + 20, y + 30,
                      ACCENT_GOLD if can_unlock else TEXT_DIM, 12)
            y += 58
        else:
            self.cat_unlock_rect = None

        # Categories list
        y += 5
        draw_text(surface, "Catégories :", px + 15, y, TEXT_SECONDARY, 13, bold=True)
        y += 20
        for cat in self.state.all_categories:
            unlocked = cat in self.state.unlocked_categories
            if unlocked:
                pygame.draw.circle(surface, ACCENT_GREEN, (px + 22, y + 6), 4)
            else:
                pygame.draw.circle(surface, TEXT_DIM, (px + 22, y + 6), 4, 1)
            color = TEXT_PRIMARY if unlocked else TEXT_DIM
            draw_text(surface, cat, px + 32, y, color, 13)
            y += 19

    def _draw_action_buttons(self, surface, cx, h):
        self.action_rects = {}
        actions = [
            ('skip', 'Skip', self.state.upgrade_counts.get('skip', 0)),
            ('reveal', 'Révéler', self.state.upgrade_counts.get('reveal', 0)),
            ('freeze', 'Freeze', self.state.upgrade_counts.get('freeze', 0)),
            ('double', 'x2 Pts', self.state.upgrade_counts.get('double', 0)),
        ]
        btn_w = 95
        btn_h = 36
        gap = 10
        total = len(actions) * btn_w + (len(actions) - 1) * gap
        x = cx - total // 2
        y = h - 52

        mouse = pygame.mouse.get_pos()
        for action_id, label, count in actions:
            rect = pygame.Rect(x, y, btn_w, btn_h)
            self.action_rects[action_id] = rect
            has = count > 0
            hover = rect.collidepoint(mouse) and has

            if hover:
                draw_glow_rect(surface, rect, BG_CARD_HOVER, ACCENT_BLUE,
                               radius=8, glow_radius=5, glow_alpha=40)
            elif has:
                draw_shadow_rect(surface, rect, BG_CARD, radius=8, border=1,
                                 border_color=BORDER_COLOR, shadow_offset=2, shadow_alpha=30)
            else:
                draw_rounded_rect(surface, rect, BG_CARD_LOCKED, radius=8, border=1,
                                  border_color=BORDER_COLOR)

            col = TEXT_PRIMARY if has else TEXT_DIM
            draw_text(surface, f"{label} ({count})", rect.centerx, rect.centery,
                      col, 13, bold=has, anchor="center")
            x += btn_w + gap


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
