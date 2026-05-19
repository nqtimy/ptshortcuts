"""LeaderboardScreen — local + global high-score display."""

import pygame

from game.config import *
from game.screens._shared import _lc, _lf, CERT_ORDER
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
