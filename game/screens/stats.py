"""StatsScreen — per-certification shortcut statistics, searchable and sortable."""

import time

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
from game.state import load_stats


class StatsScreen:
    """Per-certification shortcut statistics screen."""

    _SORT_MODES = [('rate', 'Par taux'), ('views', 'Par vues'), ('name', 'Par nom')]
    _ROW_H = 62
    _LESSON_H = 36   # lesson header row height
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
        # _display_rows: list of {'type': 'header'|'item', 'cat': str, 'sc': dict|None,
        #                         'y': int, 'h': int}
        self._display_rows = []
        self._total_height = 0
        self._scroll_y = 0.0
        self._scroll_target = 0.0
        self._sort_btn_rects = {}
        self._header_rects = {}  # {cat_name: pygame.Rect} for click hit testing
        self._back_rect = None
        self._cert_left_rect = None
        self._cert_right_rect = None
        self._cert_slide_pos = 0.0
        self._cert_slide_target = 0.0
        self._search_query = ''
        self._search_active = False
        self._search_rect = None
        # Collapse state: {cert_name: set of collapsed category names}
        self._collapsed = {}
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
        """Sort shortcuts within each lesson according to current sort mode."""
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
            sort_key = _rate
            reverse = False
        elif self._sort_mode == 'views':
            sort_key = lambda s: _entry(s)['views']
            reverse = True
        else:
            sort_key = lambda s: s.get('command_name', '').lower()
            reverse = False
        self._rows = sorted(all_sc, key=sort_key, reverse=reverse)
        self._apply_filter()

    def _apply_filter(self):
        """Recompute grouped _display_rows from _rows + search + collapse state."""
        q = self._search_query.lower().strip()
        if q:
            base = [
                sc for sc in self._rows
                if (q in (sc.get('command_name') or '').lower() or
                    q in (sc.get('context') or '').lower() or
                    q in (sc.get('category') or '').lower() or
                    q in self._fmt_keys(sc, 'keys_win').lower() or
                    q in self._fmt_keys(sc, 'keys_mac').lower())
            ]
        else:
            base = list(self._rows)

        # Group by category, preserving the order from category_names
        cats_order = list(self.cert_data.get('category_names', []))
        # Stragglers (shortcuts whose category isn't in category_names): append at end
        seen_cats = set(cats_order)
        for sc in base:
            c = sc.get('category')
            if c and c not in seen_cats:
                cats_order.append(c)
                seen_cats.add(c)

        by_cat = {}
        for sc in base:
            by_cat.setdefault(sc.get('category') or '', []).append(sc)

        collapsed = self._collapsed.setdefault(self.cert_name, set())

        rows = []
        y = 0
        for cat in cats_order:
            items = by_cat.get(cat, [])
            if not items:
                continue
            rows.append({'type': 'header', 'cat': cat, 'sc': None,
                         'count': len(items), 'y': y, 'h': self._LESSON_H})
            y += self._LESSON_H
            if cat in collapsed:
                continue
            for sc in items:
                rows.append({'type': 'item', 'cat': cat, 'sc': sc,
                             'y': y, 'h': self._ROW_H})
                y += self._ROW_H

        self._display_rows = rows
        self._total_height = y
        self._scroll_target = 0.0

    def _clamp_scroll(self, h):
        viewport_h = h - self._HEADER_H - 20
        max_scroll = max(0, self._total_height - viewport_h)
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
                handled = False
                for mode, rect in self._sort_btn_rects.items():
                    if rect.collidepoint(pos):
                        self._sort_mode = mode
                        self._build_rows()
                        handled = True
                        break
                if not handled:
                    # Lesson header toggle
                    for cat, hr in self._header_rects.items():
                        if hr.collidepoint(pos):
                            collapsed = self._collapsed.setdefault(self.cert_name, set())
                            if cat in collapsed:
                                collapsed.discard(cat)
                            else:
                                collapsed.add(cat)
                            self._apply_filter()
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
        item_count = sum(1 for r in self._display_rows if r['type'] == 'item')
        if self._search_query and item_count != total:
            summary = (f"{item_count}/{total} raccourcis   "
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
        self._header_rects = {}
        for entry in self._display_rows:
            row_y = list_top + entry['y'] - scroll_int
            if row_y + entry['h'] < list_top:
                continue
            if row_y > list_top + viewport_h:
                break
            if entry['type'] == 'header':
                hr = pygame.Rect(8, row_y, w - 16, entry['h'] - 2)
                self._header_rects[entry['cat']] = hr
                self._draw_lesson_header(surface, entry, row_y, w, mouse)
            else:
                self._draw_row(surface, entry['sc'], row_y, w, mouse, col_x)

        # Empty state when search yields no results
        if not self._display_rows and self._search_query:
            draw_text(surface, f'Aucun raccourci pour "{self._search_query}"',
                      w // 2, list_top + 60, TEXT_DIM, 14, anchor="center")

        surface.set_clip(old_clip)

        # Scroll indicator
        if self._total_height > viewport_h:
            bar_h = max(30, int(viewport_h * viewport_h / self._total_height))
            bar_y = list_top + int(self._scroll_y / max(1, self._total_height - viewport_h)
                                   * (viewport_h - bar_h))
            pygame.draw.rect(surface, BORDER_COLOR,
                             pygame.Rect(w - 6, bar_y, 4, bar_h), border_radius=2)

        draw_vignette(surface, 0.15)

    def _draw_lesson_header(self, surface, entry, row_y, w, mouse):
        """Draw a clickable lesson section header with a chevron toggle."""
        hr = pygame.Rect(8, row_y, w - 16, entry['h'] - 2)
        collapsed_set = self._collapsed.get(self.cert_name, set())
        is_collapsed = entry['cat'] in collapsed_set
        hov = hr.collidepoint(mouse)

        # Subtle band background that brightens on hover
        bg = _lc(BG_CARD, BG_CARD_HOVER, 0.5 if hov else 0.0)
        pygame.draw.rect(surface, bg, hr, border_radius=6)
        # Left accent bar (4px) — softer when collapsed
        accent_col = ACCENT_BLUE if not is_collapsed else _lc(ACCENT_BLUE, BORDER_COLOR, 0.5)
        pygame.draw.rect(surface, accent_col,
                         pygame.Rect(hr.x + 1, hr.y + 6, 3, hr.h - 12),
                         border_radius=2)
        # Chevron on the right: pointing down (expanded) or right (collapsed)
        ch_cx = hr.right - 22
        ch_cy = hr.centery
        ch_size = 5
        ch_col = _lc(TEXT_SECONDARY, TEXT_PRIMARY, 0.5 if hov else 0.0)
        if is_collapsed:
            pts = [(ch_cx - ch_size // 2, ch_cy - ch_size),
                   (ch_cx + ch_size // 2 + 1, ch_cy),
                   (ch_cx - ch_size // 2, ch_cy + ch_size)]
        else:
            pts = [(ch_cx - ch_size, ch_cy - ch_size // 2),
                   (ch_cx, ch_cy + ch_size // 2 + 1),
                   (ch_cx + ch_size, ch_cy - ch_size // 2)]
        pygame.draw.polygon(surface, ch_col, pts)

        # Label + count
        cat_label = entry['cat'] or '(sans catégorie)'
        draw_text(surface, cat_label, hr.x + 14, hr.centery,
                  TEXT_PRIMARY, 13, bold=True, anchor="midleft")
        count_str = f"{entry['count']} raccourcis"
        draw_text(surface, count_str, ch_cx - 14, hr.centery,
                  TEXT_DIM, 10, anchor="midright")

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
