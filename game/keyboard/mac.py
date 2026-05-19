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
    0x4C: 'Num Enter',  # kVK_ANSI_KeypadEnter — distinct from main Return (0x24)
}

# Cmd VK codes (for suppression)
_CMD_VK_SET = {0x37, 0x36}  # kVK_Command, kVK_RightCommand
_CAPS_LOCK_VK = 0x39        # kVK_CapsLock — suppressed entirely (Pro Tools
                            # never uses it, and pynput's Darwin backend
                            # crashes on it on macOS Tahoe).

# Modifier VKs → internal modifier names.
# Mac Command  → 'Ctrl' (Pro Tools mapping)
# Mac Option   → 'Alt'
# Mac Control  → 'Win'  (analogue of the Windows Start key)
# Mac Shift    → 'Shift'
_MAC_VK_MODIFIERS = {
    0x37: 'Ctrl',  0x36: 'Ctrl',
    0x38: 'Shift', 0x3C: 'Shift',
    0x3A: 'Alt',   0x3D: 'Alt',
    0x3B: 'Win',   0x3E: 'Win',
}

# Non-character special keys (everything that isn't a letter/digit/numpad).
_MAC_VK_SPECIAL = {
    0x31: 'Space', 0x24: 'Enter',
    0x30: 'Tab', 0x33: 'Backspace', 0x75: 'Delete', 0x35: 'Escape',
    0x73: 'Home', 0x77: 'End', 0x74: 'PageUp', 0x79: 'PageDown',
    0x7B: 'Left', 0x7C: 'Right', 0x7D: 'Down', 0x7E: 'Up',
    0x7A: 'F1', 0x78: 'F2', 0x63: 'F3', 0x76: 'F4',
    0x60: 'F5', 0x61: 'F6', 0x62: 'F7', 0x64: 'F8',
    0x65: 'F9', 0x6D: 'F10', 0x67: 'F11', 0x6F: 'F12',
}


def _vk_to_internal_name(vk):
    """Map a Mac VK code to our internal key name. None if unknown."""
    if vk in _MAC_VK_MODIFIERS:
        return _MAC_VK_MODIFIERS[vk]
    if vk in _MAC_VK_NUMPAD:
        return _MAC_VK_NUMPAD[vk]
    if vk in _MAC_VK_SPECIAL:
        return _MAC_VK_SPECIAL[vk]
    if vk in _MAC_VK_TO_QWERTY:
        return _MAC_VK_TO_QWERTY[vk]
    return None


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
        # Diagnostic: report trust status
        try:
            trusted = Quartz.AXIsProcessTrusted()
            print(f"[PTShortcuts] AXIsProcessTrusted = {trusted}",
                  file=sys.stderr, flush=True)
        except Exception:
            pass

        event_mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) | \
                     Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp) | \
                     Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)

        # Maps each modifier VK → the bit mask in CGEvent flags that indicates
        # whether ANY key of that type is currently held.
        kCmdFlag   = Quartz.kCGEventFlagMaskCommand
        kShiftFlag = Quartz.kCGEventFlagMaskShift
        kAltFlag   = Quartz.kCGEventFlagMaskAlternate
        kCtrlFlag  = Quartz.kCGEventFlagMaskControl
        _MOD_NAME_TO_FLAG = {
            'Ctrl': kCmdFlag,    # internal Ctrl == Mac Cmd
            'Shift': kShiftFlag,
            'Alt': kAltFlag,
            'Win': kCtrlFlag,    # internal Win == Mac Control
        }

        def _callback(proxy, event_type, event, refcon):
            try:
                vk = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventKeycode)

                # Always absorb Caps Lock — Pro Tools never uses it, and
                # leaving it on would change the keyboard LED state.
                if vk == _CAPS_LOCK_VK:
                    return None

                name = _vk_to_internal_name(vk)
                flags = Quartz.CGEventGetFlags(event)
                cmd_held = bool(flags & kCmdFlag)

                if event_type == Quartz.kCGEventFlagsChanged:
                    # Modifier press/release: derive state from the relevant
                    # flag bit, since flagsChanged doesn't tell us press vs
                    # release directly.
                    if name in _MOD_NAME_TO_FLAG:
                        held = bool(flags & _MOD_NAME_TO_FLAG[name])
                        with handler.lock:
                            if held:
                                handler.pressed_modifiers.add(name)
                            else:
                                handler.pressed_modifiers.discard(name)
                        # Suppress Cmd events so macOS doesn't intercept
                        # Cmd-shortcuts (Cmd+M minimize, Cmd+H hide, etc.).
                        if name == 'Ctrl':
                            return None
                    return event

                if event_type == Quartz.kCGEventKeyDown:
                    if name is not None and name not in _MOD_NAME_TO_FLAG:
                        with handler.lock:
                            handler.pressed_keys.add(name)
                            combo = frozenset(
                                handler.pressed_modifiers | {name})
                            handler._last_combo = combo
                            handler._combo_time = time.time()
                            handler.events.append(
                                (time.time(), 'combo', combo))
                    # Suppress when Cmd is held to prevent macOS shortcuts.
                    if cmd_held:
                        return None
                    return event

                if event_type == Quartz.kCGEventKeyUp:
                    if name is not None and name not in _MOD_NAME_TO_FLAG:
                        with handler.lock:
                            handler.pressed_keys.discard(name)
                    if cmd_held:
                        return None
                    return event
            except Exception:
                pass
            return event

        # Try tap locations in order: session is best, but on macOS 26+ with
        # ad-hoc signed apps it sometimes refuses; annotated-session is a
        # softer alternative that doesn't require the same entitlement.
        tap = None
        for tap_loc, tap_name in (
            (Quartz.kCGSessionEventTap, 'session'),
            (Quartz.kCGAnnotatedSessionEventTap, 'annotated-session'),
        ):
            try:
                tap = Quartz.CGEventTapCreate(
                    tap_loc,
                    Quartz.kCGHeadInsertEventTap,
                    Quartz.kCGEventTapOptionDefault,
                    event_mask,
                    _callback,
                    None,
                )
            except Exception as e:
                print(f"[PTShortcuts] CGEventTapCreate({tap_name}) raised: {e}",
                      file=sys.stderr, flush=True)
                tap = None
            if tap is not None:
                print(f"[PTShortcuts] CGEventTap installed at {tap_name}.",
                      file=sys.stderr, flush=True)
                break
            print(f"[PTShortcuts] CGEventTapCreate({tap_name}) returned None.",
                  file=sys.stderr, flush=True)
        if tap is None:
            print("[PTShortcuts] All tap locations failed. Either Accessibility "
                  "permission is missing (after rebuild it must be re-granted) "
                  "or the ad-hoc-signed binary is denied on macOS 26+.",
                  file=sys.stderr, flush=True)
            return None

        src = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(), src, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
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

    def stop_win_suppression(self):
        if self._cmd_tap is not None:
            try:
                import Quartz
                Quartz.CGEventTapEnable(self._cmd_tap, False)
            except Exception:
                pass
            self._cmd_tap = None

    def start(self):
        """On macOS we no longer use pynput's Listener — its Darwin backend
        crashes in HIToolbox TSM when constructing an NSEvent for Caps Lock
        on macOS Tahoe (and uses a listen-only tap, so we can't filter Caps
        Lock upstream). Instead our CGEventTap below is the SOLE input source
        for the game: it tracks all modifiers, all key presses, and feeds
        directly into pressed_modifiers / pressed_keys / events.
        """
        self._running = True
        if self._cmd_tap is None:
            self._cmd_tap = _try_install_cmd_suppression(self)

    def start_win_suppression(self, game_hwnd=None):
        # Tap is already installed in start(); kept for cross-platform symmetry.
        if self._cmd_tap is None:
            self._cmd_tap = _try_install_cmd_suppression(self)

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
