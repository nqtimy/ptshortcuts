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
_font_paths = None  # dict: {'sans': path, 'mono': path, 'mono_bold': path}


def _find_custom_fonts():
    """Locate bundled .ttf fonts in assets/ (Space Grotesk + JetBrains Mono).

    Prefers static Regular/Bold over Variable for more predictable rasterization
    at small sizes (the variable font's hinting can produce asymmetric glyphs
    like a 'b' with a smaller counter than an 'o').
    """
    global _font_paths
    if getattr(sys, '_MEIPASS', None):
        assets = os.path.join(sys._MEIPASS, 'assets')
    else:
        assets = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets')
    paths = {'sans': None, 'sans_bold': None, 'mono': None, 'mono_bold': None}
    variable_sans = None
    if os.path.isdir(assets):
        for f in os.listdir(assets):
            low = f.lower()
            full = os.path.join(assets, f)
            if not (low.endswith('.ttf') or low.endswith('.otf')):
                continue
            is_sg = 'spacegrotesk' in low or 'space-grotesk' in low or 'space_grotesk' in low
            is_jb = 'jetbrainsmono' in low or 'jetbrains-mono' in low
            if is_sg:
                if 'variable' in low:
                    variable_sans = full
                elif 'bold' in low:
                    paths['sans_bold'] = full
                elif 'regular' in low or 'medium' in low:
                    # Prefer Regular; Medium is fallback only
                    if paths['sans'] is None or 'regular' in low:
                        paths['sans'] = full
            elif is_jb:
                if 'bold' in low:
                    paths['mono_bold'] = full
                else:
                    paths['mono'] = full
    # Fall back to variable if no static found
    if paths['sans'] is None:
        paths['sans'] = variable_sans
    if paths['sans_bold'] is None:
        paths['sans_bold'] = variable_sans
    _font_paths = paths


def get_font(size, bold=False, mono=False):
    """Get or create a cached font. Prefers Space Grotesk (sans) / JetBrains Mono (mono).

    Set mono=True to get a monospace font for score counters, cost badges,
    and keycap labels (matches design v4 which uses JetBrains Mono there).
    """
    key = (size, bold, mono)
    if key not in _fonts:
        if _font_paths is None:
            _find_custom_fonts()

        # Try bundled TTFs first (prefer dedicated Bold instance over faux-bold)
        path = None
        use_faux_bold = False
        if mono:
            path = _font_paths.get('mono_bold') if bold else _font_paths.get('mono')
            if path is None:
                path = _font_paths.get('mono') or _font_paths.get('mono_bold')
        else:
            if bold:
                path = _font_paths.get('sans_bold') or _font_paths.get('sans')
                # Faux-bold only if we had to fall back to the regular file
                use_faux_bold = (path == _font_paths.get('sans'))
            else:
                path = _font_paths.get('sans')
        if path:
            try:
                font = pygame.font.Font(path, size)
                if use_faux_bold:
                    font.set_bold(True)
                _fonts[key] = font
                return font
            except Exception:
                pass

        names = FONT_NAMES_MONO if mono else (FONT_NAMES_BOLD if bold else FONT_NAMES)
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
# Easings & color helpers (Design v4)
# ---------------------------------------------------------------------------

def ease_out_cubic(t):
    """Standard ease-out-cubic — used for the animated score counter."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_sine(t):
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def lerp_color(c1, c2, t):
    """Linear interpolate two RGB tuples at ratio t in [0,1]."""
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def lerp_color_stops(stops, t):
    """Multi-stop gradient sampling. `stops` = [(t0, rgb), (t1, rgb), ...]."""
    t = max(0.0, min(1.0, t))
    ordered = sorted(stops, key=lambda s: s[0])
    for i in range(len(ordered) - 1):
        t0, c0 = ordered[i]
        t1, c1 = ordered[i + 1]
        if t <= t1:
            local = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return lerp_color(c0, c1, local)
    return ordered[-1][1]


def frame_lerp(k, dt):
    """Frame-rate independent lerp factor. Use as: v += (target - v) * frame_lerp(k, dt).

    k is the 'strength' at 60fps (0..1). At dt=1/60, returns ~k.
    """
    return 1.0 - (1.0 - k) ** (dt * 60.0)


# ---------------------------------------------------------------------------
# Surface cache for glow / shadow effects
# ---------------------------------------------------------------------------

def _scale_alpha(surf, alpha):
    """Multiply per-pixel alpha by `alpha` (0-255). Returns a new surface.

    `Surface.set_alpha()` interacts unpredictably with per-pixel alpha on macOS
    (SDL_ttf can produce surfaces where global alpha overrides per-pixel alpha,
    making rendered text appear as a solid colored bounding box). Multiplying
    with BLEND_RGBA_MULT is reliable across platforms.
    """
    if alpha >= 255:
        return surf
    if alpha <= 0:
        return pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    out = surf.convert_alpha() if pygame.display.get_init() and pygame.display.get_surface() else surf.copy()
    overlay = pygame.Surface(out.get_size(), pygame.SRCALPHA)
    overlay.fill((255, 255, 255, alpha))
    out.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


_glow_cache = {}


def _get_glow_surface(w, h, color, radius=20, alpha=80):
    """Cached soft-glow surface for a rounded rectangle.

    Design v4: produces a falloff that fades to 0 at the outer edge. The inner
    bright region is intentionally narrow so the glow reads as a halo around
    the shape, not a bright block filling its interior.
    """
    key = (w, h, color, radius, alpha)
    if key not in _glow_cache:
        pad = radius
        surf = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        # Many thin expanding rings from outside in. Each ring blits ONTO the
        # already-existing alpha so we use BLEND_RGBA_MAX to keep the brightest
        # pixel per-sample (rather than stacking) — softer, no hard banding.
        steps = max(12, radius)
        for i in range(steps, 0, -1):
            t = i / steps                      # 1 = outermost, 0 = innermost
            a = int(alpha * (1.0 - t) ** 2.2)  # quadratic falloff
            if a <= 0:
                continue
            expand = int(radius * t)
            r = pygame.Rect(pad - expand, pad - expand,
                            w + expand * 2, h + expand * 2)
            ring = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            pygame.draw.rect(ring, (*color, a), (0, 0, r.w, r.h),
                             border_radius=radius + expand)
            surf.blit(ring, r.topleft, special_flags=pygame.BLEND_RGBA_MAX)
        _glow_cache[key] = surf
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
        shadow_surf = _scale_alpha(shadow_surf, 120)
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
        glow_surf = _scale_alpha(glow_surf, glow_alpha // offset)
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
        # Pressed: purple glow (design v4 accent)
        draw_glow_rect(surface, key_rect, ACCENT_PURPLE, ACCENT_PURPLE, radius=8,
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


# ---------------------------------------------------------------------------
# Design v4: gradient fills, radial halos, padlock icon
# ---------------------------------------------------------------------------

def draw_gradient_rect(surface, rect, color_a, color_b, radius=0,
                       direction="horizontal"):
    """Rounded rect filled with a linear gradient from color_a to color_b.

    direction: "horizontal" (a→b left→right) or "vertical" (a→b top→bottom)
    or "diagonal" (a→b top-left→bottom-right).
    """
    r = pygame.Rect(rect)
    if r.w <= 0 or r.h <= 0:
        return
    grad = pygame.Surface((r.w, r.h), pygame.SRCALPHA)

    if direction == "horizontal":
        for gx in range(r.w):
            t = gx / max(1, r.w - 1)
            col = lerp_color(color_a, color_b, t)
            pygame.draw.line(grad, (*col, 255), (gx, 0), (gx, r.h))
    elif direction == "vertical":
        for gy in range(r.h):
            t = gy / max(1, r.h - 1)
            col = lerp_color(color_a, color_b, t)
            pygame.draw.line(grad, (*col, 255), (0, gy), (r.w, gy))
    else:  # diagonal
        max_d = r.w + r.h
        for gy in range(r.h):
            for gx in range(r.w):
                t = (gx + gy) / max(1, max_d - 1)
                col = lerp_color(color_a, color_b, t)
                grad.set_at((gx, gy), (*col, 255))

    if radius > 0:
        mask = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, r.w, r.h),
                         border_radius=radius)
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surface.blit(grad, r.topleft)


def draw_text_gradient(surface, text, x, y, stops, size=24, bold=True,
                       anchor="center", mono=False,
                       glow_color=None, glow_alpha=0):
    """Draw text filled with a horizontal multi-stop gradient.

    stops: [(t_offset, (r,g,b)), ...]  e.g. [(0,WHITE),(0.5,PURPLE),(1,PINK)]
    Optional glow halo behind (blurred offset passes of `glow_color`).
    """
    font = get_font(size, bold=bold, mono=mono)
    base = font.render(text, True, (255, 255, 255))
    tw, th = base.get_size()
    rect = base.get_rect(**{anchor: (x, y)})

    if glow_color and glow_alpha > 0:
        for offset in (3, 2, 1):
            gs = font.render(text, True, glow_color)
            gs = _scale_alpha(gs, glow_alpha // offset)
            for dx, dy in ((-offset, 0), (offset, 0), (0, -offset), (0, offset)):
                gr = gs.get_rect(**{anchor: (x + dx, y + dy)})
                surface.blit(gs, gr)

    grad = pygame.Surface((tw, th), pygame.SRCALPHA)
    for gx in range(tw):
        t = gx / max(1, tw - 1)
        col = lerp_color_stops(stops, t)
        pygame.draw.line(grad, (*col, 255), (gx, 0), (gx, th))
    # Mask with text alpha (only where the text has ink)
    grad.blit(base, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surface.blit(grad, rect.topleft)
    return rect


def draw_radial_halo(surface, cx, cy, radius_x, radius_y, color, alpha=30,
                     falloff=2.0):
    """Draw an elliptical radial glow centered at (cx, cy).

    Used for the top-bar purple halo and menu background accent.
    """
    rx, ry = max(1, int(radius_x)), max(1, int(radius_y))
    halo = pygame.Surface((rx * 2, ry * 2), pygame.SRCALPHA)
    steps = 12
    for i in range(steps, 0, -1):
        t = i / steps
        a = int(alpha * (1.0 - t) ** falloff)
        if a <= 0:
            continue
        ew = int(rx * 2 * t)
        eh = int(ry * 2 * t)
        pygame.draw.ellipse(halo, (*color, a),
                            (rx - ew // 2, ry - eh // 2, ew, eh))
    surface.blit(halo, (cx - rx, cy - ry))


def draw_padlock(surface, cx, cy, size=16, color=None):
    """Minimal padlock glyph centered at (cx, cy). `size` ≈ total height."""
    c = color or TEXT_DIM
    body_w = int(size * 0.80)
    body_h = int(size * 0.55)
    body_x = cx - body_w // 2
    body_y = cy - body_h // 2 + int(size * 0.12)
    pygame.draw.rect(surface, c, (body_x, body_y, body_w, body_h),
                     border_radius=max(2, size // 7))
    # Shackle (arc U-shape above the body)
    shackle_w = int(size * 0.55)
    shackle_h = int(size * 0.55)
    shackle_x = cx - shackle_w // 2
    shackle_y = body_y - shackle_h + int(size * 0.18)
    arc_rect = pygame.Rect(shackle_x, shackle_y, shackle_w, shackle_h)
    pygame.draw.arc(surface, c, arc_rect, math.radians(15), math.radians(165),
                    max(2, size // 8))
    # Keyhole dot
    pygame.draw.circle(surface, BG_COLOR, (cx, body_y + body_h // 2),
                       max(1, size // 12))


def draw_progress_bar(surface, rect, pct, fill_stops,
                      bg_color=None, radius=None):
    """Horizontal progress bar with a multi-stop gradient fill.

    fill_stops: list of (t, rgb) passed to lerp_color_stops per pixel column.
    """
    r = pygame.Rect(rect)
    bg = bg_color if bg_color is not None else BG_PANEL
    rad = r.h // 2 if radius is None else radius
    pygame.draw.rect(surface, bg, r, border_radius=rad)
    if pct <= 0:
        return
    fill_w = max(1, int(r.w * max(0.0, min(1.0, pct))))
    fill = pygame.Surface((fill_w, r.h), pygame.SRCALPHA)
    for gx in range(fill_w):
        t = gx / max(1, r.w - 1)  # gradient spans the FULL bar, not just fill
        col = lerp_color_stops(fill_stops, t)
        pygame.draw.line(fill, (*col, 255), (gx, 0), (gx, r.h))
    mask = pygame.Surface((fill_w, r.h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, fill_w, r.h),
                     border_radius=rad)
    fill.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surface.blit(fill, r.topleft)


def draw_corner_frame(surface, rect, color, length=60, thickness=1, alpha=128):
    """Decorative L-shaped corner marks (4 corners of `rect`).

    Used by the menu screen as ambient frame accents.
    """
    r = pygame.Rect(rect)
    layer = pygame.Surface(r.size, pygame.SRCALPHA)
    c = (*color, alpha)
    x0, y0 = 0, 0
    x1, y1 = r.w, r.h
    # top-left
    pygame.draw.line(layer, c, (x0, y0), (x0 + length, y0), thickness)
    pygame.draw.line(layer, c, (x0, y0), (x0, y0 + length), thickness)
    # top-right
    pygame.draw.line(layer, c, (x1, y0), (x1 - length, y0), thickness)
    pygame.draw.line(layer, c, (x1, y0), (x1, y0 + length), thickness)
    # bottom-left
    pygame.draw.line(layer, c, (x0, y1 - 1), (x0 + length, y1 - 1), thickness)
    pygame.draw.line(layer, c, (x0, y1), (x0, y1 - length), thickness)
    # bottom-right
    pygame.draw.line(layer, c, (x1, y1 - 1), (x1 - length, y1 - 1), thickness)
    pygame.draw.line(layer, c, (x1, y1), (x1, y1 - length), thickness)
    surface.blit(layer, r.topleft)


def draw_flash(surface, color, alpha=0.15):
    """Draw a full-screen color flash overlay."""
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((*color, int(alpha * 255)))
    surface.blit(overlay, (0, 0))


def draw_border_glow(surface, color, intensity=0.5):
    """Draw a glowing border around the screen (for timer critical).

    Uses SRCALPHA gradient surfaces blitted on each edge — alpha fades from
    `alpha` at the outer edge to 0 at `thickness` inward (quadratic falloff).
    """
    w, h = surface.get_size()
    thickness = 30
    alpha = int(intensity * 120)
    if alpha <= 0:
        return

    # Top edge
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
    bc = ACCENT_PURPLE if hover else border_color
    draw_shadow_rect(surface, r, bg, radius=10, border=2, border_color=bc,
                     shadow_offset=3, shadow_alpha=40)

    if icon:
        draw_text(surface, icon, r.x + 14, r.centery, ACCENT_PURPLE if not hover else TEXT_PRIMARY,
                  text_size, bold=True, anchor="midleft")
        draw_text(surface, text, r.x + 46, r.centery, text_color, text_size, anchor="midleft")
    else:
        draw_text(surface, text, r.centerx, r.centery, text_color, text_size,
                  bold=True, anchor="center")
    return r
