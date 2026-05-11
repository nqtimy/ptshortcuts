"""macOS keyboard handler using pynput + optional CGEventTap for Cmd suppression.

Modifier mapping (Pro Tools Mac → internal names shared with Windows):
  Command (Cmd)  → 'Ctrl'   (Pro Tools Mac Command = Windows Ctrl)
  Option  (Opt)  → 'Alt'
  Control (Ctrl) → 'Win'
  Shift          → 'Shift'

Physical key position: Mac virtual key codes (Carbon kVK_ANSI_*) map to
QWERTY character names, identical to keys_win / keys_mac JSON fields.

Cmd key suppression: requires Accessibility permissions (System Settings →
Privacy & Security → Accessibility → grant to PTShortcuts.app).  If the
permission is not granted the CGEventTap creation silently fails and Cmd keys
pass through normally (game still works, but Cmd+H/Q etc. remain active).
"""

import sys
import threading
import time
from collections import deque

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

from game.keyboard.base import BaseKeyboardHandler

# ---------------------------------------------------------------------------
# Modifier mapping (Mac keys → internal names)
# ---------------------------------------------------------------------------

MODIFIER_MAP = {
    Key.cmd:     'Ctrl',  Key.cmd_l:   'Ctrl',  Key.cmd_r:   'Ctrl',
    Key.ctrl:    'Win',   Key.ctrl_l:  'Win',   Key.ctrl_r:  'Win',
    Key.alt:     'Alt',   Key.alt_l:   'Alt',   Key.alt_r:   'Alt',
    Key.shift:   'Shift', Key.shift_l: 'Shift', Key.shift_r: 'Shift',
}

SPECIAL_KEY_MAP = {
    Key.space:      'Space',
    Key.enter:      'Enter',
    Key.tab:        'Tab',
    Key.backspace:  'Backspace',
    Key.delete:     'Delete',
    Key.up:         'Up',
    Key.down:       'Down',
    Key.left:       'Left',
    Key.right:      'Right',
    Key.esc:        'Escape',
    Key.f1: 'F1', Key.f2: 'F2', Key.f3: 'F3', Key.f4: 'F4',
    Key.f5: 'F5', Key.f6: 'F6', Key.f7: 'F7', Key.f8: 'F8',
    Key.f9: 'F9', Key.f10: 'F10', Key.f11: 'F11', Key.f12: 'F12',
    Key.home:       'Home',
    Key.end:        'End',
    Key.page_up:    'PageUp',
    Key.page_down:  'PageDown',
    Key.caps_lock:  'CapsLock',
}

# Mac keyboards may not expose Insert / NumLock — add only if pynput defines them
for _opt_name, _opt_label in (('insert', 'Insert'), ('num_lock', 'NumLock')):
    _opt_key = getattr(Key, _opt_name, None)
    if _opt_key is not None:
        SPECIAL_KEY_MAP[_opt_key] = _opt_label

# ---------------------------------------------------------------------------
# Mac virtual key codes (kVK_ANSI_*) → QWERTY character names
# These are PHYSICAL key positions (layout-independent) just like Windows scan codes.
# ---------------------------------------------------------------------------

_MAC_VK_TO_QWERTY = {
    # Home row
    0x00: 'A', 0x01: 'S', 0x02: 'D', 0x03: 'F', 0x04: 'H', 0x05: 'G',
    # Bottom row
    0x06: 'Z', 0x07: 'X', 0x08: 'C', 0x09: 'V', 0x0B: 'B',
    # Top row
    0x0C: 'Q', 0x0D: 'W', 0x0E: 'E', 0x0F: 'R', 0x10: 'Y', 0x11: 'T',
    # Number row (Mac VKC order is not sequential)
    0x12: '1', 0x13: '2', 0x14: '3', 0x15: '4', 0x16: '6', 0x17: '5',
    0x19: '9', 0x1A: '7', 0x1C: '8', 0x1D: '0',
    # Symbols
    0x18: '=', 0x1B: '-', 0x1E: ']', 0x21: '[',
    0x27: "'", 0x29: ';', 0x2A: '\\', 0x2B: ',', 0x2C: '/', 0x2F: '.', 0x32: '`',
    # Rest of letters
    0x1F: 'O', 0x20: 'U', 0x22: 'I', 0x23: 'P',
    0x25: 'L', 0x26: 'J', 0x28: 'K',
    0x2D: 'N', 0x2E: 'M',
}

# Mac numpad virtual key codes
_MAC_VK_NUMPAD = {
    0x52: 'Num0', 0x53: 'Num1', 0x54: 'Num2', 0x55: 'Num3',
    0x56: 'Num4', 0x57: 'Num5', 0x58: 'Num6', 0x59: 'Num7',
    0x5B: 'Num8', 0x5C: 'Num9',
    0x41: 'Num.', 0x4B: 'Num/', 0x43: 'Num*', 0x4E: 'Num-', 0x45: 'Num+',
}

# Cmd VK codes (for suppression)
_CMD_VK_SET = {0x37, 0x36}  # kVK_Command, kVK_RightCommand


def name_is_modifier(key):
    return key in MODIFIER_MAP


def key_to_name(key):
    """Convert a pynput key to our internal name string."""
    if key in MODIFIER_MAP:
        return MODIFIER_MAP[key]
    if key in SPECIAL_KEY_MAP:
        return SPECIAL_KEY_MAP[key]
    if isinstance(key, KeyCode):
        vk = key.vk
        if vk is not None:
            if vk in _MAC_VK_NUMPAD:
                return _MAC_VK_NUMPAD[vk]
            if vk in _MAC_VK_TO_QWERTY:
                return _MAC_VK_TO_QWERTY[vk]
        # Fallback: use char
        if key.char is not None and key.char.isprintable() and len(key.char) == 1:
            return key.char.upper()
    return None


# ---------------------------------------------------------------------------
# Cmd suppression via CGEventTap (requires Accessibility permission)
# ---------------------------------------------------------------------------

def _try_install_cmd_suppression(handler):
    """Install a CGEventTap that suppresses Cmd+key events to prevent macOS
    from intercepting shortcuts like Cmd+M (minimize), Cmd+H (hide), etc.

    Since suppressing at the head of the event chain also prevents pynput from
    seeing the event, this callback injects the key into the handler directly.

    Silently no-ops if Quartz is unavailable or permission is denied.
    Must be called from the main thread (CGEventTap requires a run loop).
    """
    try:
        import Quartz  # pyobjc-framework-Quartz
        import AppKit  # noqa: F401 — needed to start NSRunLoop
    except ImportError as e:
        print(f"[PTShortcuts] CGEventTap suppression unavailable: {e}",
              file=sys.stderr, flush=True)
        return None

    try:

        event_mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) | \
                     Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp) | \
                     Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)

        kCmdFlag = Quartz.kCGEventFlagMaskCommand

        def _callback(proxy, event_type, event, refcon):
            try:
                vk = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventKeycode)
                flags = Quartz.CGEventGetFlags(event)
                cmd_held = bool(flags & kCmdFlag)

                # FlagsChanged: track Cmd press/release ourselves
                if event_type == Quartz.kCGEventFlagsChanged:
                    if vk in _CMD_VK_SET:
                        with handler.lock:
                            if cmd_held:
                                handler.pressed_modifiers.add('Ctrl')
                            else:
                                handler.pressed_modifiers.discard('Ctrl')
                        return None  # suppress Cmd event from reaching OS
                    return event  # other modifier — let pynput handle

                # KeyDown/KeyUp while Cmd is held: inject + suppress
                if cmd_held and event_type in (Quartz.kCGEventKeyDown,
                                                Quartz.kCGEventKeyUp):
                    name = _MAC_VK_NUMPAD.get(vk) or _MAC_VK_TO_QWERTY.get(vk)
                    if name is not None:
                        with handler.lock:
                            if event_type == Quartz.kCGEventKeyDown:
                                handler.pressed_keys.add(name)
                                combo = frozenset(
                                    handler.pressed_modifiers | {name})
                                handler._last_combo = combo
                                handler._combo_time = time.time()
                                handler.events.append(
                                    (time.time(), 'combo', combo))
                            else:
                                handler.pressed_keys.discard(name)
                    return None  # suppress so macOS doesn't run its shortcut
            except Exception:
                pass
            return event

        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            event_mask,
            _callback,
            None,
        )
        if tap is None:
            print("[PTShortcuts] CGEventTapCreate returned None — "
                  "Accessibility permission likely missing or app needs restart "
                  "after permission was granted.",
                  file=sys.stderr, flush=True)
            return None

        src = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(), src, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        print("[PTShortcuts] Cmd suppression CGEventTap installed.",
              file=sys.stderr, flush=True)
        return tap
    except Exception as e:
        print(f"[PTShortcuts] CGEventTap install failed: {e}",
              file=sys.stderr, flush=True)
        return None


class KeyboardHandler(BaseKeyboardHandler):
    """macOS keyboard handler — pynput listener + optional Cmd suppression."""

    def __init__(self):
        self.pressed_modifiers = set()
        self.pressed_keys = set()
        self.events = deque(maxlen=100)
        self.lock = threading.Lock()
        self.listener = None
        self._running = False
        self._last_combo = None
        self._combo_time = 0.0
        self._cmd_tap = None

    # start_win_suppression / stop_win_suppression: best-effort on Mac

    def start_win_suppression(self, game_hwnd=None):
        """Install CGEventTap for Cmd key suppression (no-op if unavailable)."""
        self._cmd_tap = _try_install_cmd_suppression(self)

    def stop_win_suppression(self):
        if self._cmd_tap is not None:
            try:
                import Quartz
                Quartz.CGEventTapEnable(self._cmd_tap, False)
            except Exception:
                pass
            self._cmd_tap = None

    def start(self):
        self._running = True
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False,
        )
        self.listener.daemon = True
        self.listener.start()

    def stop(self):
        self._running = False
        if self.listener:
            self.listener.stop()
            self.listener = None

    def _on_press(self, key):
        if not self._running:
            return
        name = key_to_name(key)
        if name is None:
            return
        with self.lock:
            if name in ('Win', 'Ctrl', 'Shift', 'Alt'):
                self.pressed_modifiers.add(name)
            else:
                self.pressed_keys.add(name)
                combo = frozenset(self.pressed_modifiers | {name})
                self._last_combo = combo
                self._combo_time = time.time()
                self.events.append((time.time(), 'combo', combo))

    def _on_release(self, key):
        if not self._running:
            return
        name = key_to_name(key)
        if name is None:
            return
        with self.lock:
            if name in ('Win', 'Ctrl', 'Shift', 'Alt'):
                self.pressed_modifiers.discard(name)
            else:
                self.pressed_keys.discard(name)

    def get_current_keys(self):
        with self.lock:
            return set(self.pressed_modifiers | self.pressed_keys)

    def get_last_combo(self):
        with self.lock:
            combo = self._last_combo
            self._last_combo = None
            return combo

    def peek_last_combo(self):
        with self.lock:
            if self._last_combo is None:
                return None
            return frozenset(
                k.upper() if len(k) == 1 else k for k in self._last_combo)

    def consume_last_combo(self):
        with self.lock:
            self._last_combo = None

    def poll_events(self):
        with self.lock:
            events = list(self.events)
            self.events.clear()
            return events

    def check_combo_v2(self, detect_options):
        combo = self.get_last_combo()
        if combo is None:
            return None
        actual = frozenset(k.upper() if len(k) == 1 else k for k in combo)
        return actual in detect_options

    def check_modifier_only(self, expected_modifiers):
        with self.lock:
            if not self.pressed_modifiers:
                return None
            return self.pressed_modifiers == expected_modifiers

    def check_modifiers_for_click(self, expected_modifiers):
        with self.lock:
            return frozenset(self.pressed_modifiers) == expected_modifiers

    def clear(self):
        with self.lock:
            self.pressed_modifiers.clear()
            self.pressed_keys.clear()
            self._last_combo = None
            self.events.clear()
