"""Game constants and configuration.

Palette & typography migrated to Design v4 — neon violet/pink on deep dark bg.
Hex references:
  bg=#07070f, bgCard=#0e0e1a, bgCard2=#13131f, bgPanel=#17172a
  border=#1f1f38, borderHi=#3a3a70
  textPrimary=#eeeeff, textSecondary=#7777aa, textDim=#3a3a60
  accent=#a855f7 (violet), pink=#e879f9, green=#22d3ee (cyan), red=#f43f5e,
  orange=#fb923c, gold=#facc15
"""

import sys

# Platform
IS_MAC = sys.platform == 'darwin'

# Window
MIN_WIDTH = 960
MIN_HEIGHT = 540
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
FPS = 60

# ── Colors (Design v4: dark violet/pink neon) ────────────────────────────────
BG_COLOR = (7, 7, 15)            # #07070f
BG_SECONDARY = (14, 14, 26)      # #0e0e1a (bgCard)
BG_CARD = (14, 14, 26)           # #0e0e1a
BG_CARD_2 = (19, 19, 31)         # #13131f
BG_PANEL = (23, 23, 42)          # #17172a
BG_CARD_HOVER = (28, 28, 50)
BG_CARD_LOCKED = (10, 10, 18)
BG_CONTEXT = BG_CARD_2           # context sits inside card, no yellow tint anymore

BORDER_COLOR = (31, 31, 56)      # #1f1f38
BORDER_HIGHLIGHT = (58, 58, 112) # #3a3a70

TEXT_PRIMARY = (238, 238, 255)   # #eeeeff
TEXT_SECONDARY = (119, 119, 170) # #7777aa
TEXT_DIM = (90, 90, 130)         # slightly brighter than design's #3a3a60 for pygame readability
TEXT_LOCKED = (58, 58, 96)       # #3a3a60 — use for deep-locked elements

# Accent colors
ACCENT_PURPLE = (168, 85, 247)   # #a855f7 — primary accent
ACCENT_PINK = (232, 121, 249)    # #e879f9 — secondary gradient partner
ACCENT_CYAN = (34, 211, 238)     # #22d3ee — success / timer full
ACCENT_GREEN = ACCENT_CYAN       # alias (design uses cyan as "green/success")
ACCENT_RED = (244, 63, 94)       # #f43f5e
ACCENT_ORANGE = (251, 146, 60)   # #fb923c
ACCENT_GOLD = (250, 204, 21)     # #facc15

# Kept for AZERTY/QWERTY dual display: blue stays distinct from violet
ACCENT_BLUE = (96, 165, 250)     # #60a5fa — used only for dual-display contrast

# Timer bar colors (>50% cyan, >25% gold, <25% red+pulse)
TIMER_FULL = ACCENT_CYAN
TIMER_MID = ACCENT_GOLD
TIMER_LOW = ACCENT_RED

# Combo color progression (design v4)
COMBO_COLORS = {
    1: TEXT_DIM,
    2: ACCENT_PURPLE,
    3: ACCENT_PURPLE,
    5: ACCENT_CYAN,
    8: ACCENT_GOLD,
    10: ACCENT_ORANGE,
    15: ACCENT_RED,
    20: ACCENT_PINK,
}

# Points per difficulty
POINTS = {1: 10, 2: 25, 3: 60}

# Timer (seconds)
TIMER_BASE = 10.0
TIMER_MIN = 3.0
TIMER_DECAY_PER_LEVEL = 0.3

# Difficulty 3 unlock threshold (lifetime score)
DIFF3_UNLOCK_SCORE = 200

# Lesson unlock cost: round(150 * 1.5^i) per lesson index (design v4)
CATEGORY_UNLOCK_COST_BASE = 150
CATEGORY_UNLOCK_COST_MULT = 1.5

# ── Score-gated Powers (Design v4) ────────────────────────────────────────────
# Powers unlock automatically once the player's LIFETIME score reaches
# `unlock_cost`. Using a power then deducts `use_cost` from AVAILABLE score.
POWERS = {
    "skip": {
        "name": "Skip",
        "description": "Passer le raccourci",
        "icon": ">>",
        "unlock_cost": 0,
        "use_cost": 50,
        "color": (119, 119, 170),   # TEXT_SECONDARY (neutral)
        "order": 0,
    },
    "reveal": {
        "name": "Révéler",
        "description": "Voir la réponse",
        "icon": "()",
        "unlock_cost": 150,
        "use_cost": 80,
        "color": ACCENT_PINK,
        "order": 1,
    },
    "freeze": {
        "name": "Freeze",
        "description": "Geler le timer 5s",
        "icon": "**",
        "unlock_cost": 350,
        "use_cost": 60,
        "color": ACCENT_CYAN,
        "order": 2,
    },
    "double": {
        "name": "Double",
        "description": "x2 pts pendant 15s",
        "icon": "x2",
        "unlock_cost": 700,
        "use_cost": 120,
        "color": ACCENT_GOLD,
        "order": 3,
    },
}

# Backwards-compat alias so legacy imports of UPGRADES don't break during the
# transition. Phase B will migrate state.py to POWERS; legacy reads still work.
UPGRADES = {
    k: {
        "name": v["name"],
        "description": v["description"],
        "icon": v["icon"],
        "base_cost": v["use_cost"],
        "cost_mult": 1.0,
    }
    for k, v in POWERS.items()
}

# Key display names (for rendering pressed keys)
KEY_DISPLAY = {
    "Win": "Win",
    "Ctrl": "Ctrl",
    "Shift": "Shift",
    "Alt": "Alt",
    "Space": "Space",
    "Enter": "Enter",
    "Tab": "Tab",
    "Backspace": "Back",
    "Delete": "Del",
    "Escape": "Esc",
}

# ── Visual / Animation constants ──────────────────────────────────────────────

# Screen shake
SHAKE_CORRECT = 4
SHAKE_WRONG = 8
SHAKE_GAME_OVER = 16
SHAKE_DECAY = 0.85

# Particle counts
PARTICLES_CORRECT = 40
PARTICLES_CORRECT_HIGH = 80
PARTICLES_WRONG = 15
PARTICLES_MILESTONE = 120
PARTICLES_EMBER_RATE = 3
MAX_PARTICLES = 400

# Combo milestones (firework ring at these values)
COMBO_MILESTONES = {5, 10, 15, 20, 25, 30, 50}

# Shadow
SHADOW_OFFSET = 4
SHADOW_ALPHA = 60

# Score counter animation duration (seconds) — ease-out cubic, design v4
SCORE_ANIM_DURATION = 0.6

# ── Typography (Design v4: Space Grotesk + JetBrains Mono) ───────────────────
# Bahnschrift/Segoe UI kept as fallback for Windows without Space Grotesk
# installed (commonly available since Win10).
FONT_NAMES = [
    'Space Grotesk', 'Inter', 'Bahnschrift', 'Segoe UI', 'Calibri', 'Arial',
    'sans-serif',
]
FONT_NAMES_BOLD = FONT_NAMES  # same preference order, bold flag set at render
FONT_NAMES_MONO = [
    'JetBrains Mono', 'Fira Code', 'Cascadia Mono', 'Consolas', 'Menlo',
    'Courier New', 'monospace',
]
