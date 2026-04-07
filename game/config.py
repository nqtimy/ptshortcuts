"""Game constants and configuration."""

import sys

# Platform
IS_MAC = sys.platform == 'darwin'

# Window
MIN_WIDTH = 960
MIN_HEIGHT = 540
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
FPS = 60

# Colors (dark DAW theme)
BG_COLOR = (24, 24, 30)
BG_SECONDARY = (32, 32, 40)
BG_PANEL = (38, 38, 48)
BG_CARD = (44, 44, 56)
BG_CARD_HOVER = (54, 54, 68)
BG_CARD_LOCKED = (30, 30, 36)
BG_CONTEXT = (50, 45, 30)
BORDER_COLOR = (60, 60, 75)
BORDER_HIGHLIGHT = (100, 100, 130)

TEXT_PRIMARY = (230, 230, 240)
TEXT_SECONDARY = (160, 160, 175)
TEXT_DIM = (100, 100, 115)
TEXT_LOCKED = (70, 70, 80)

ACCENT_BLUE = (80, 140, 240)
ACCENT_GREEN = (60, 200, 120)
ACCENT_RED = (220, 60, 70)
ACCENT_ORANGE = (240, 160, 40)
ACCENT_GOLD = (255, 200, 50)
ACCENT_PURPLE = (160, 100, 240)

TIMER_FULL = (60, 200, 120)
TIMER_MID = (240, 200, 40)
TIMER_LOW = (220, 60, 70)

# Combo colors
COMBO_COLORS = {
    1: TEXT_PRIMARY,
    2: (150, 200, 255),
    3: (100, 180, 255),
    5: ACCENT_GOLD,
    8: ACCENT_ORANGE,
    10: ACCENT_RED,
    15: ACCENT_PURPLE,
}

# Points per difficulty
POINTS = {1: 10, 2: 25, 3: 60}

# Timer (seconds)
TIMER_BASE = 10.0
TIMER_MIN = 3.0
TIMER_DECAY_PER_LEVEL = 0.3

# Difficulty 3 unlock threshold (score)
DIFF3_UNLOCK_SCORE = 200

# Category unlock cost (points to unlock next category)
CATEGORY_UNLOCK_COST_BASE = 150
CATEGORY_UNLOCK_COST_MULT = 1.5

# Upgrades
UPGRADES = {
    "skip": {
        "name": "Skip",
        "description": "Passer le raccourci actuel",
        "icon": ">>",
        "base_cost": 50,
        "cost_mult": 1.3,
    },
    "reveal": {
        "name": "Révéler",
        "description": "Afficher la réponse",
        "icon": "?!",
        "base_cost": 80,
        "cost_mult": 1.4,
    },
    "freeze": {
        "name": "Freeze",
        "description": "Geler le timer 5s",
        "icon": "**",
        "base_cost": 60,
        "cost_mult": 1.3,
    },
    "double": {
        "name": "x2 Points",
        "description": "Double points 15s",
        "icon": "x2",
        "base_cost": 120,
        "cost_mult": 1.5,
    },
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

# --- Visual / Animation constants ---

# Screen shake
SHAKE_CORRECT = 4        # pixels, small shake on correct
SHAKE_WRONG = 8          # medium shake on wrong
SHAKE_GAME_OVER = 16     # big shake on game over
SHAKE_DECAY = 0.85       # multiply each frame

# Particle counts
PARTICLES_CORRECT = 40
PARTICLES_CORRECT_HIGH = 80
PARTICLES_WRONG = 15
PARTICLES_MILESTONE = 120
PARTICLES_EMBER_RATE = 3   # embers per frame at high combo
MAX_PARTICLES = 400

# Combo milestones (firework ring at these values)
COMBO_MILESTONES = {5, 10, 15, 20, 25, 30, 50}

# Shadow
SHADOW_OFFSET = 4
SHADOW_ALPHA = 60

# Font preference order (rounded, impactful)
FONT_NAMES = ['Bahnschrift', 'Segoe UI', 'Calibri', 'Arial', 'sans-serif']
FONT_NAMES_BOLD = ['Bahnschrift', 'Segoe UI', 'Calibri', 'Arial', 'sans-serif']
