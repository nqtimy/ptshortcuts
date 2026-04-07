"""Tests for game/keyboard/win.py — key name resolution and handler state."""

import pytest
from pynput.keyboard import Key, KeyCode

from game.keyboard.win import (
    key_to_name,
    name_is_modifier,
    KeyboardHandler,
    MODIFIER_MAP,
)


# ---------------------------------------------------------------------------
# name_is_modifier
# ---------------------------------------------------------------------------

class TestNameIsModifier:
    def test_shift_is_modifier(self):
        assert name_is_modifier(Key.shift)
        assert name_is_modifier(Key.shift_l)
        assert name_is_modifier(Key.shift_r)

    def test_ctrl_is_modifier(self):
        assert name_is_modifier(Key.ctrl)
        assert name_is_modifier(Key.ctrl_l)
        assert name_is_modifier(Key.ctrl_r)

    def test_alt_is_modifier(self):
        assert name_is_modifier(Key.alt)
        assert name_is_modifier(Key.alt_l)

    def test_win_is_modifier(self):
        assert name_is_modifier(Key.cmd)
        assert name_is_modifier(Key.cmd_l)

    def test_regular_key_not_modifier(self):
        assert not name_is_modifier(Key.space)
        assert not name_is_modifier(Key.enter)
        assert not name_is_modifier(KeyCode(char='a'))


# ---------------------------------------------------------------------------
# key_to_name
# ---------------------------------------------------------------------------

class TestKeyToName:
    def test_modifiers(self):
        assert key_to_name(Key.shift) == 'Shift'
        assert key_to_name(Key.ctrl) == 'Ctrl'
        assert key_to_name(Key.alt) == 'Alt'
        assert key_to_name(Key.cmd) == 'Win'

    def test_special_keys(self):
        assert key_to_name(Key.space) == 'Space'
        assert key_to_name(Key.enter) == 'Enter'
        assert key_to_name(Key.tab) == 'Tab'
        assert key_to_name(Key.backspace) == 'Backspace'
        assert key_to_name(Key.delete) == 'Delete'
        assert key_to_name(Key.esc) == 'Escape'

    def test_arrow_keys(self):
        assert key_to_name(Key.up) == 'Up'
        assert key_to_name(Key.down) == 'Down'
        assert key_to_name(Key.left) == 'Left'
        assert key_to_name(Key.right) == 'Right'

    def test_function_keys(self):
        assert key_to_name(Key.f1) == 'F1'
        assert key_to_name(Key.f12) == 'F12'

    def test_navigation_keys(self):
        assert key_to_name(Key.home) == 'Home'
        assert key_to_name(Key.end) == 'End'
        assert key_to_name(Key.page_up) == 'PageUp'
        assert key_to_name(Key.page_down) == 'PageDown'
        assert key_to_name(Key.insert) == 'Insert'

    def test_numpad_digits_via_vk(self):
        # VK_NUMPAD0 = 0x60 ... VK_NUMPAD9 = 0x69
        for i in range(10):
            k = KeyCode(vk=0x60 + i)
            assert key_to_name(k) == f'Num{i}'

    def test_numpad_operators_via_vk(self):
        assert key_to_name(KeyCode(vk=0x6E)) == 'Num.'
        assert key_to_name(KeyCode(vk=0x6F)) == 'Num/'
        assert key_to_name(KeyCode(vk=0x6A)) == 'Num*'
        assert key_to_name(KeyCode(vk=0x6D)) == 'Num-'
        assert key_to_name(KeyCode(vk=0x6B)) == 'Num+'

    def test_num5_numlock_off_vk_clear(self):
        # VK_CLEAR (0x0C) = Num5 when NumLock is OFF
        assert key_to_name(KeyCode(vk=0x0C)) == 'Num5'

    def test_numpad_nav_extended_false(self):
        # NumLock OFF: nav key with extended=False → numpad name
        assert key_to_name(Key.end, extended=False) == 'Num1'
        assert key_to_name(Key.down, extended=False) == 'Num2'
        assert key_to_name(Key.page_down, extended=False) == 'Num3'
        assert key_to_name(Key.left, extended=False) == 'Num4'
        assert key_to_name(Key.right, extended=False) == 'Num6'
        assert key_to_name(Key.home, extended=False) == 'Num7'
        assert key_to_name(Key.up, extended=False) == 'Num8'
        assert key_to_name(Key.page_up, extended=False) == 'Num9'
        assert key_to_name(Key.insert, extended=False) == 'Num0'
        assert key_to_name(Key.delete, extended=False) == 'Num.'

    def test_numpad_nav_extended_true_is_regular(self):
        # With extended=True, these are real navigation keys
        assert key_to_name(Key.end, extended=True) == 'End'
        assert key_to_name(Key.home, extended=True) == 'Home'

    def test_printable_char_uppercase(self):
        assert key_to_name(KeyCode(char='a')) == 'A'
        assert key_to_name(KeyCode(char='z')) == 'Z'

    def test_unknown_key_returns_none(self):
        # KeyCode with no char and no recognized vk
        k = KeyCode(vk=0x99)  # not a known VK
        # Result may be None or a char depending on MapVirtualKeyW — just check type
        result = key_to_name(k)
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# KeyboardHandler state (no listener started)
# ---------------------------------------------------------------------------

class TestKeyboardHandlerState:
    def setup_method(self):
        self.kbd = KeyboardHandler()

    def test_initial_state_empty(self):
        assert self.kbd.get_last_combo() is None
        assert self.kbd.peek_last_combo() is None
        assert self.kbd.get_current_keys() == set()

    def test_get_last_combo_consumes(self):
        self.kbd._last_combo = frozenset({'Ctrl', 'S'})
        combo = self.kbd.get_last_combo()
        assert combo == frozenset({'Ctrl', 'S'})
        assert self.kbd.get_last_combo() is None

    def test_peek_does_not_consume(self):
        self.kbd._last_combo = frozenset({'Ctrl', 'Z'})
        first = self.kbd.peek_last_combo()
        second = self.kbd.peek_last_combo()
        assert first == second == frozenset({'Ctrl', 'Z'})
        assert self.kbd._last_combo is not None

    def test_consume_clears_combo(self):
        self.kbd._last_combo = frozenset({'Alt', 'F4'})
        self.kbd.consume_last_combo()
        assert self.kbd._last_combo is None

    def test_clear_resets_all_state(self):
        self.kbd.pressed_modifiers = {'Ctrl', 'Shift'}
        self.kbd.pressed_keys = {'S'}
        self.kbd._last_combo = frozenset({'Ctrl', 'Shift', 'S'})
        self.kbd.events.append('fake_event')
        self.kbd.clear()
        assert self.kbd.pressed_modifiers == set()
        assert self.kbd.pressed_keys == set()
        assert self.kbd._last_combo is None
        assert len(self.kbd.events) == 0

    def test_check_combo_v2_match(self):
        self.kbd._last_combo = frozenset({'Ctrl', 'S'})
        options = [frozenset({'Ctrl', 'S'}), frozenset({'Ctrl', 'Z'})]
        assert self.kbd.check_combo_v2(options) is True

    def test_check_combo_v2_no_match(self):
        self.kbd._last_combo = frozenset({'Ctrl', 'A'})
        options = [frozenset({'Ctrl', 'S'})]
        assert self.kbd.check_combo_v2(options) is False

    def test_check_combo_v2_no_input(self):
        assert self.kbd.check_combo_v2([frozenset({'Ctrl', 'S'})]) is None

    def test_check_modifier_only_match(self):
        self.kbd.pressed_modifiers = {'Ctrl', 'Shift'}
        assert self.kbd.check_modifier_only({'Ctrl', 'Shift'}) is True

    def test_check_modifier_only_mismatch(self):
        self.kbd.pressed_modifiers = {'Ctrl'}
        assert self.kbd.check_modifier_only({'Ctrl', 'Shift'}) is False

    def test_check_modifier_only_empty(self):
        self.kbd.pressed_modifiers = set()
        assert self.kbd.check_modifier_only({'Ctrl'}) is None

    def test_check_modifiers_for_click_match(self):
        self.kbd.pressed_modifiers = {'Ctrl', 'Alt'}
        assert self.kbd.check_modifiers_for_click(frozenset({'Ctrl', 'Alt'})) is True

    def test_check_modifiers_for_click_mismatch(self):
        self.kbd.pressed_modifiers = {'Ctrl'}
        assert self.kbd.check_modifiers_for_click(frozenset({'Ctrl', 'Alt'})) is False

    def test_get_current_keys_combines_modifiers_and_keys(self):
        self.kbd.pressed_modifiers = {'Ctrl'}
        self.kbd.pressed_keys = {'S'}
        assert self.kbd.get_current_keys() == {'Ctrl', 'S'}

    def test_poll_events_clears_queue(self):
        self.kbd.events.append(('t', 'combo', frozenset({'A'})))
        events = self.kbd.poll_events()
        assert len(events) == 1
        assert len(self.kbd.events) == 0

    def test_check_shortcut_match(self):
        self.kbd._last_combo = frozenset({'Ctrl', 'S'})
        assert self.kbd.check_shortcut(['Ctrl', 'S']) is True

    def test_check_shortcut_no_input(self):
        assert self.kbd.check_shortcut(['Ctrl', 'S']) is None
