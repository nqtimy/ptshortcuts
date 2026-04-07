"""Abstract base class for keyboard handlers.

Defines the interface that all platform-specific implementations must satisfy.
Windows: game.keyboard.win.KeyboardHandler
Mac (future): game.keyboard.mac.KeyboardHandler
"""

import abc


class BaseKeyboardHandler(abc.ABC):
    """Platform-agnostic keyboard handler interface."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def start(self):
        """Start the keyboard listener."""

    @abc.abstractmethod
    def stop(self):
        """Stop the keyboard listener."""

    def start_win_suppression(self, game_hwnd):
        """Suppress the OS Win/Cmd key while the game window is focused.

        Default no-op; Windows implementation overrides this.
        game_hwnd: native window handle (HWND on Windows, ignored on other platforms).
        """

    def stop_win_suppression(self):
        """Remove the Win/Cmd key suppression hook. Default no-op."""

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def get_current_keys(self):
        """Return the set of all currently pressed key names (modifiers + keys)."""

    @abc.abstractmethod
    def get_last_combo(self):
        """Return and consume the last recorded combo frozenset, or None."""

    @abc.abstractmethod
    def peek_last_combo(self):
        """Return the last combo frozenset WITHOUT consuming it, or None."""

    @abc.abstractmethod
    def consume_last_combo(self):
        """Discard the last recorded combo."""

    @abc.abstractmethod
    def poll_events(self):
        """Return and clear the list of raw keyboard events."""

    # ------------------------------------------------------------------
    # Shortcut matching
    # ------------------------------------------------------------------

    def check_shortcut(self, expected_keys):
        """Check if the last combo matches expected_keys (legacy helper).

        Returns True (match), False (wrong combo), None (no input yet).
        """
        combo = self.get_last_combo()
        if combo is None:
            return None
        expected = frozenset(k.upper() if len(k) == 1 else k for k in expected_keys)
        actual = frozenset(k.upper() if len(k) == 1 else k for k in combo)
        return actual == expected

    @abc.abstractmethod
    def check_combo_v2(self, detect_options):
        """Check if the last combo matches any frozenset in detect_options.

        detect_options: list of frozensets from loader._build_detect_info.
        Returns True (match), False (wrong combo pressed), None (no input yet).
        """

    @abc.abstractmethod
    def check_modifier_only(self, expected_modifiers):
        """Check if exactly expected_modifiers are currently held.

        Returns True (match), False (wrong set held), None (nothing held).
        """

    @abc.abstractmethod
    def check_modifiers_for_click(self, expected_modifiers):
        """Check if currently held modifiers exactly match expected_modifiers.

        Returns True or False (no None — used for modifier_click detection).
        """

    @abc.abstractmethod
    def clear(self):
        """Reset all pressed key state and pending combos."""
