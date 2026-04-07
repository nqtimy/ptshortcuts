"""Pygame rendering utilities — stylized with shadows, glow, rounded fonts."""

import math
import os
import sys
import time

import pygame

from game.config import *
from game.particles import RingParticle


# ---------------------------------------------------------------------------
# Font system
# ---------------------------------------------------------------------------

_fonts = {}
_font_path = None  # Custom .ttf path if found


def _find_custom_font():
    """Look for a custom .ttf font in assets/."""
    global _font_path
    if getattr(sys, '_MEIPASS', None):
        assets = os.path.join(sys._MEIPASS, 'assets')
    else:
        assets = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets')
    if os.path.isdir(assets):
        for f in os.listdir(assets):
            if f.lower().endswith('.ttf') or f.lower().endswith('.otf'):
                _font_path = os.path.join(assets, f)
                return
    _font_path = ''  # Mark as checked, none found


def get_font(size, bold=False):
    """Get or create a cached font. Prefers rounded system fonts."""
    key = (size, bold)
    if key not in _fonts:
        if _font_path is None:
            _find_custom_font()

        # Try custom font first
        if _font_path:
            try:
                _fonts[key] = pygame.font.Font(_font_path, size)
                return _fonts[key]
            except Exception:
                pass

        # Try system fonts (rounded, impactful)
        names = FONT_NAMES_BOLD if bold else FONT_NAMES
        for name in names:
            try:
                font = pygame.font.SysFont(name, size, bold=bold)
                if font and font.get_height() > 0:
                    _fonts[key] = font
                    return font
            except Exception:
                continue
        _fonts[key] = pygame.font.Font(None, size)
    return _fonts[key]


# ---------------------------------------------------------------------------
# Surface cache for glow / shadow effects
# ---------------------------------------------------------------------------

_glow_cache = {}


def _get_glow_surface(w, h, color, radius=20, alpha=80):
    """Create a cached glow surface (blurred rectangle)."""
    key = (w, h, color, radius, alpha)
    if key not in _glow_cache:
        surf = pygame.Surface((w + radius * 2, h + radius * 2), pygame.SRCALPHA)
        # Draw layered expanding rects for glow
        steps = min(radius, 10)
        for i in range(steps):
            t = i / steps
            a = int(alpha * (1.0 - t) * (1.0 - t))
            expand = int(radius * t)
            r = pygame.Rect(radius - expand, radius - expand,
                            w + expand * 2, h + expand * 2)
            pygame.draw.rect(surf, (*color, a), r, border_radius=radius)
        _glow_cache[key] = surf
        # Limit cache size
        if len(_glow_cache) > 200:
            oldest = next(iter(_glow_cache))
            del _glow_cache[oldest]
    return _glow_cache[key]


# ---------------------------------------------------------------------------
# Core drawing functions
# ---------------------------------------------------------------------------

def draw_text(surface, text, x, y, color=TEXT_PRIMARY, size=24, bold=False,
              anchor="topleft", max_width=None, shadow=False, shadow_color=None):
    """Draw text with anchor support and optional drop shadow."""
    font = get_font(size, bold)
    if max_width:
        rendered = font.render(text, True, color)
        while rendered.get_width() > max_width and len(text) > 3:
            text = text[:-4] + "..."
            rendered = font.render(text, True, color)
    else:
        rendered = font.render(text, True, color)
    rect = rendered.get_rect(**{anchor: (x, y)})

    if shadow:
        sc = shadow_color or (0, 0, 0)
        shadow_surf = font.render(text, True, sc)
        shadow_rect = shadow_surf.get_rect(**{anchor: (x + 2, y + 2)})
        # Apply alpha
        shadow_surf.set_alpha(120)
        surface.blit(shadow_surf, shadow_rect)

    surface.blit(rendered, rect)
    return rect


def draw_text_glow(surface, text, x, y, color, glow_color=None, size=24,
                   bold=True, anchor="center", glow_alpha=60):
    """Draw text with a color glow halo behind it."""
    gc = glow_color or color
    font = get_font(size, bold)

    # Glow layers (3 offset passes)
    for offset in [3, 2, 1]:
        glow_surf = font.render(text, True, gc)
        glow_surf.set_alpha(glow_alpha // offset)
        for dx, dy in [(-offset, 0), (offset, 0), (0, -offset), (0, offset)]:
            r = glow_surf.get_rect(**{anchor: (x + dx, y + dy)})
            surface.blit(glow_surf, r)

    # Main text
    rendered = font.render(text, True, color)
    rect = rendered.get_rect(**{anchor: (x, y)})
    surface.blit(rendered, rect)
    return rect


def draw_rounded_rect(surface, rect, color, radius=10, border=0, border_color=None):
    """Draw a rounded rectangle."""
    r = pygame.Rect(rect)
    if border > 0 and border_color:
        pygame.draw.rect(surface, border_color, r, border_radius=radius)
        inner = r.inflate(-border * 2, -border * 2)
        pygame.draw.rect(surface, color, inner, border_radius=max(0, radius - border))
    else:
        pygame.draw.rect(surface, color, r, border_radius=radius)


def draw_shadow_rect(surface, rect, color, radius=10, border=0, border_color=None,
                     shadow_offset=None, shadow_alpha=None):
    """Draw a rounded rectangle with a drop shadow."""
    so = shadow_offset or SHADOW_OFFSET
    sa = shadow_alpha or SHADOW_ALPHA
    r = pygame.Rect(rect)

    # Shadow
    shadow_rect = r.move(so, so)
    shadow_surf = pygame.Surface((shadow_rect.w, shadow_rect.h), pygame.SRCALPHA)
    pygame.draw.rect(shadow_surf, (0, 0, 0, sa), (0, 0, shadow_rect.w, shadow_rect.h),
                     border_radius=radius)
    surface.blit(shadow_surf, shadow_rect.topleft)

    # Main rect
    draw_rounded_rect(surface, r, color, radius, border, border_color)


def draw_glow_rect(surface, rect, color, glow_color, radius=10, glow_radius=12,
                   glow_alpha=50):
    """Draw a rounded rectangle with an outer glow."""
    r = pygame.Rect(rect)
    glow_surf = _get_glow_surface(r.w, r.h, glow_color, glow_radius, glow_alpha)
    surface.blit(glow_surf, (r.x - glow_radius, r.y - glow_radius))
    pygame.draw.rect(surface, color, r, border_radius=radius)


def draw_key_cap(surface, text, x, y, size=36, pressed=False):
    """Draw a keyboard key cap with 3D depth effect."""
    font = get_font(size - 8, bold=True)
    text_surf = font.render(text, True, TEXT_PRIMARY if not pressed else BG_COLOR)
    tw, th = text_surf.get_size()
    pad_x, pad_y = 16, 10
    w = tw + pad_x * 2
    h = th + pad_y * 2

    key_rect = pygame.Rect(x, y, w, h)

    if pressed:
        # Pressed: glow + flat
        draw_glow_rect(surface, key_rect, ACCENT_BLUE, ACCENT_BLUE, radius=8,
                       glow_radius=8, glow_alpha=80)
    else:
        # 3D effect: bottom border darker
        bottom_rect = pygame.Rect(x, y + 2, w, h)
        pygame.draw.rect(surface, (30, 30, 40), bottom_rect, border_radius=8)
        pygame.draw.rect(surface, BG_CARD, key_rect, border_radius=8)
        pygame.draw.rect(surface, BORDER_HIGHLIGHT, key_rect, width=1, border_radius=8)

    surface.blit(text_surf, (x + pad_x, y + pad_y))
    return w


def draw_key_combo(surface, keys, cx, cy, size=36, pressed_keys=None):
    """Draw a series of key caps centered at (cx, cy)."""
    if pressed_keys is None:
        pressed_keys = set()

    font = get_font(size - 8, bold=True)
    gap = 10
    plus_font = get_font(size - 12, False)
    plus_width = plus_font.render("+", True, TEXT_DIM).get_width() + 8

    # Measure total width
    total_w = 0
    key_widths = []
    for k in keys:
        ts = font.render(k, True, TEXT_PRIMARY)
        w = ts.get_width() + 32
        key_widths.append(w)
        total_w += w
    total_w += (len(keys) - 1) * (plus_width + gap)

    # Draw centered
    x = cx - total_w // 2
    y = cy - (font.get_height() + 20) // 2

    for i, k in enumerate(keys):
        pressed = k in pressed_keys or k.upper() in pressed_keys
        w = draw_key_cap(surface, k, x, y, size, pressed)
        x += w + gap // 2
        if i < len(keys) - 1:
            plus_surf = plus_font.render("+", True, TEXT_DIM)
            pr = plus_surf.get_rect(center=(x + plus_width // 2, cy))
            surface.blit(plus_surf, pr)
            x += plus_width + gap // 2
    return total_w


def draw_key_sequence(surface, steps, cx, cy, size=36, current_step=0, show_all=False):
    """Draw a key sequence: step1 -> step2 -> step3, centered at (cx, cy).

    steps: list of lists, e.g. [["Ctrl","Alt","1"], ["B"]]
    current_step: which step the player is on (for highlighting completed steps)
    show_all: if True, show all steps (reveal mode); else dim future steps
    """
    font = get_font(size - 8, bold=True)
    arrow_font = get_font(size - 8, False)
    arrow_text = " > "
    arrow_w = arrow_font.render(arrow_text, True, TEXT_DIM).get_width()

    # Measure total width
    step_widths = []
    for step_keys in steps:
        combo_w = 0
        plus_font = get_font(size - 12, False)
        plus_w = plus_font.render("+", True, TEXT_DIM).get_width() + 8
        for j, k in enumerate(step_keys):
            ts = font.render(k, True, TEXT_PRIMARY)
            combo_w += ts.get_width() + 32
            if j < len(step_keys) - 1:
                combo_w += plus_w + 10
        step_widths.append(combo_w)

    total_w = sum(step_widths) + (len(steps) - 1) * arrow_w
    x = cx - total_w // 2
    y_pos = cy - (font.get_height() + 20) // 2

    for si, step_keys in enumerate(steps):
        completed = si < current_step
        active = si == current_step
        for ki, k in enumerate(step_keys):
            pressed = completed
            w = draw_key_cap(surface, k, x, y_pos, size, pressed=pressed)
            x += w + 5
            if ki < len(step_keys) - 1:
                plus_font = get_font(size - 12, False)
                plus_surf = plus_font.render("+", True, TEXT_DIM)
                plus_w = plus_surf.get_width() + 8
                pr = plus_surf.get_rect(center=(x + plus_w // 2, cy))
                surface.blit(plus_surf, pr)
                x += plus_w + 5
        if si < len(steps) - 1:
            color = ACCENT_GREEN if completed else TEXT_DIM
            arrow_surf = arrow_font.render(arrow_text, True, color)
            ar = arrow_surf.get_rect(center=(x + arrow_w // 2, cy))
            surface.blit(arrow_surf, ar)
            x += arrow_w


def draw_timer_bar(surface, x, y, width, height, ratio, frozen=False):
    """Draw the timer bar with glow edge."""
    # Background
    bg_rect = pygame.Rect(x, y, width, height)
    pygame.draw.rect(surface, BG_SECONDARY, bg_rect, border_radius=height // 2)

    if ratio <= 0:
        return

    # Color
    if frozen:
        color = ACCENT_BLUE
    elif ratio > 0.5:
        color = TIMER_FULL
    elif ratio > 0.25:
        t = (ratio - 0.25) / 0.25
        color = (
            int(TIMER_LOW[0] + (TIMER_MID[0] - TIMER_LOW[0]) * t),
            int(TIMER_LOW[1] + (TIMER_MID[1] - TIMER_LOW[1]) * t),
            int(TIMER_LOW[2] + (TIMER_MID[2] - TIMER_LOW[2]) * t),
        )
    else:
        color = TIMER_LOW

    # Fill bar
    fill_w = max(height, int(width * ratio))  # Min width = height for round cap
    fill_rect = pygame.Rect(x, y, fill_w, height)
    pygame.draw.rect(surface, color, fill_rect, border_radius=height // 2)

    # Glow at the edge of the bar
    edge_x = x + fill_w - 2
    glow_surf = pygame.Surface((20, height + 10), pygame.SRCALPHA)
    for i in range(10):
        a = int(60 * (1.0 - i / 10))
        pygame.draw.rect(glow_surf, (*color, a), (10 - i, 5 - i // 2, i * 2, height + i))
    surface.blit(glow_surf, (edge_x - 10, y - 5))

    # Pulsing effect when low
    if ratio < 0.25 and not frozen:
        pulse = abs(math.sin(time.time() * 8)) * 0.4
        overlay = pygame.Surface((fill_w, height), pygame.SRCALPHA)
        overlay.fill((*ACCENT_RED, int(pulse * 255)))
        surface.blit(overlay, (x, y))


def draw_combo_text(surface, combo, cx, cy):
    """Draw the combo multiplier with glow and pulse."""
    if combo <= 0:
        return

    # Determine color
    color = TEXT_PRIMARY
    for threshold in sorted(COMBO_COLORS.keys(), reverse=True):
        if combo >= threshold:
            color = COMBO_COLORS[threshold]
            break

    # Pulsing size
    base_size = min(56, 30 + combo * 2)
    pulse = abs(math.sin(time.time() * 4)) * 4 if combo >= 3 else 0
    size = int(base_size + pulse)
    text = f"x{combo}"

    # Glow for combo >= 3
    if combo >= 3:
        draw_text_glow(surface, text, cx, cy, color, glow_alpha=40 + combo * 3,
                       size=size, bold=True, anchor="center")
    else:
        draw_text(surface, text, cx, cy, color, size, bold=True, anchor="center",
                  shadow=True)


def draw_particles(surface, particles):
    """Render particles with glow effect for bright ones."""
    now = time.time()
    for p in particles:
        if isinstance(p, RingParticle):
            _draw_ring(surface, p, now)
            continue
        alpha = p.alpha(now)
        if alpha <= 0:
            continue
        size = max(1, int(p.size * alpha))
        r = max(0, min(255, int(p.color[0] * alpha)))
        g = max(0, min(255, int(p.color[1] * alpha)))
        b = max(0, min(255, int(p.color[2] * alpha)))
        ix, iy = int(p.x), int(p.y)

        if p.glow and size >= 2:
            # Draw glow halo
            glow_size = size * 3
            glow_surf = pygame.Surface((glow_size * 2, glow_size * 2), pygame.SRCALPHA)
            glow_alpha = int(alpha * 40)
            pygame.draw.circle(glow_surf, (r, g, b, glow_alpha),
                               (glow_size, glow_size), glow_size)
            surface.blit(glow_surf, (ix - glow_size, iy - glow_size))

        pygame.draw.circle(surface, (r, g, b), (ix, iy), size)


def _draw_ring(surface, ring, now):
    """Draw an expanding ring particle."""
    if not ring.alive(now):
        return
    alpha = ring.alpha(now)
    r = int(ring.radius(now))
    if r < 1:
        return
    color = ring.color
    a = int(alpha * 200)
    # Draw ring on transparent surface
    d = r * 2 + 10
    ring_surf = pygame.Surface((d, d), pygame.SRCALPHA)
    c = d // 2
    w = max(1, int(ring.width * alpha))
    pygame.draw.circle(ring_surf, (*color, a), (c, c), r, w)
    # Outer glow
    if r > 5:
        pygame.draw.circle(ring_surf, (*color, a // 3), (c, c), r + 3, max(1, w + 2))
    surface.blit(ring_surf, (int(ring.x) - c, int(ring.y) - c))


def draw_score_popups(surface, popups):
    """Render floating score popups with scale effect."""
    now = time.time()
    for popup in popups:
        alpha = popup.alpha(now)
        if alpha <= 0:
            continue
        size = popup.current_size(now)
        r = max(0, min(255, int(popup.color[0] * alpha)))
        g = max(0, min(255, int(popup.color[1] * alpha)))
        b = max(0, min(255, int(popup.color[2] * alpha)))
        color = (r, g, b)
        # Shadow
        draw_text(surface, popup.text, int(popup.x) + 2, int(popup.y) + 2,
                  (0, 0, 0), size, bold=True, anchor="center")
        draw_text(surface, popup.text, int(popup.x), int(popup.y),
                  color, size, bold=True, anchor="center")


def draw_flash(surface, color, alpha=0.15):
    """Draw a full-screen color flash overlay."""
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((*color, int(alpha * 255)))
    surface.blit(overlay, (0, 0))


def draw_border_glow(surface, color, intensity=0.5):
    """Draw a glowing border around the screen (for timer critical)."""
    w, h = surface.get_size()
    thickness = 30
    alpha = int(intensity * 120)
    if alpha <= 0:
        return

    # Top
    for i in range(thickness):
        a = int(alpha * (1.0 - i / thickness))
        pygame.draw.line(surface, (*color, 0), (0, i), (w, i))
        # Use surface for alpha
    # More efficient: draw gradient rects
    grad = pygame.Surface((w, thickness), pygame.SRCALPHA)
    for i in range(thickness):
        a = int(alpha * (1.0 - i / thickness) ** 2)
        pygame.draw.line(grad, (*color, a), (0, i), (w, i))
    surface.blit(grad, (0, 0))
    # Bottom (flip)
    flipped = pygame.transform.flip(grad, False, True)
    surface.blit(flipped, (0, h - thickness))
    # Left
    grad_v = pygame.Surface((thickness, h), pygame.SRCALPHA)
    for i in range(thickness):
        a = int(alpha * (1.0 - i / thickness) ** 2)
        pygame.draw.line(grad_v, (*color, a), (i, 0), (i, h))
    surface.blit(grad_v, (0, 0))
    # Right (flip)
    flipped_v = pygame.transform.flip(grad_v, True, False)
    surface.blit(flipped_v, (w - thickness, 0))


def draw_vignette(surface, intensity=0.3):
    """Draw a subtle vignette (darkened edges)."""
    w, h = surface.get_size()
    vig = pygame.Surface((w, h), pygame.SRCALPHA)
    # Simple: dark corners via radial gradient approximation
    max_dist = math.sqrt((w / 2) ** 2 + (h / 2) ** 2)
    # Use fewer steps for performance
    steps = 8
    for i in range(steps):
        t = i / steps
        radius = int(max_dist * (1.0 - t * 0.5))
        a = int(intensity * 255 * t * t)
        if a > 0 and radius > 0:
            pygame.draw.ellipse(vig, (0, 0, 0, a),
                                (w // 2 - radius, h // 2 - radius, radius * 2, radius * 2))
    surface.blit(vig, (0, 0))


def draw_button(surface, text, rect, color=BG_CARD, hover=False, text_color=TEXT_PRIMARY,
                text_size=20, border_color=BORDER_COLOR, icon=None):
    """Draw a clickable button with shadow."""
    r = pygame.Rect(rect)
    bg = BG_CARD_HOVER if hover else color
    bc = ACCENT_BLUE if hover else border_color
    draw_shadow_rect(surface, r, bg, radius=10, border=2, border_color=bc,
                     shadow_offset=3, shadow_alpha=40)

    if icon:
        draw_text(surface, icon, r.x + 14, r.centery, ACCENT_BLUE if not hover else TEXT_PRIMARY,
                  text_size, bold=True, anchor="midleft")
        draw_text(surface, text, r.x + 46, r.centery, text_color, text_size, anchor="midleft")
    else:
        draw_text(surface, text, r.centerx, r.centery, text_color, text_size,
                  bold=True, anchor="center")
    return r
