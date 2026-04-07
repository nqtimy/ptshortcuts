"""Keyboard handler — platform dispatch.

All existing imports (from game.keyboard import KeyboardHandler) remain valid.
"""

import sys

if sys.platform == 'win32':
    from game.keyboard.win import KeyboardHandler
elif sys.platform == 'darwin':
    from game.keyboard.mac import KeyboardHandler
else:
    raise ImportError(
        f"Unsupported platform: {sys.platform}. "
        "Supported platforms: Windows (win32), macOS (darwin)."
    )

__all__ = ['KeyboardHandler']
