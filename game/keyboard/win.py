"""Windows keyboard handler using pynput + Win32 low-level hook."""

import ctypes
import threading
import time
from collections import deque

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

import ctypes.wintypes

from game.keyboard.base import BaseKeyboardHandler

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# Proper 64-bit type declarations for Win32 API
_kernel32.GetModuleHandleW.restype = ctypes.wintypes.HMODULE
_kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]
_user32.SetWindowsHookExW.restype = ctypes.wintypes.HHOOK
_user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int, ctypes.c_void_p, ctypes.wintypes.HINSTANCE, ctypes.wintypes.DWORD,
]
_user32.UnhookWindowsHookEx.argtypes = [ctypes.wintypes.HHOOK]
_user32.CallNextHookEx.restype = ctypes.wintypes.LPARAM
_user32.CallNextHookEx.argtypes = [
    ctypes.wintypes.HHOOK, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
]
_user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short

# Low-level keyboard hook for Win / Alt+Tab suppression
_WH_KEYBOARD_LL = 13
_WM_KEYDOWN = 0x0100
_WM_KEYUP = 0x0101
_WM_SYSKEYDOWN = 0x0104
_WM_SYSKEYUP = 0x0105
_WIN_VK_SET = {0x5B, 0x5C}  # VK_LWIN, VK_RWIN
_VK_TAB = 0x09
_VK_MENU = 0x12   # Alt (either side)


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('vkCode', ctypes.wintypes.DWORD),
        ('scanCode', ctypes.wintypes.DWORD),
        ('flags', ctypes.wintypes.DWORD),
        ('time', ctypes.wintypes.DWORD),
        ('dwExtraInfo', ctypes.POINTER(ctypes.wintypes.DWORD)),
    ]


# Callback type for LowLevelKeyboardProc (LRESULT CALLBACK)
_HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.wintypes.LPARAM,    # LRESULT return
    ctypes.c_int,              # nCode
    ctypes.wintypes.WPARAM,    # wParam
    ctypes.wintypes.LPARAM,    # lParam (raw pointer)
)


# Mapping pynput keys to our internal key names
MODIFIER_MAP = {
    Key.shift: 'Shift', Key.shift_l: 'Shift', Key.shift_r: 'Shift',
    Key.ctrl: 'Ctrl', Key.ctrl_l: 'Ctrl', Key.ctrl_r: 'Ctrl',
    Key.alt: 'Alt', Key.alt_l: 'Alt', Key.alt_r: 'Alt',
    Key.cmd: 'Win', Key.cmd_l: 'Win', Key.cmd_r: 'Win',
}

SPECIAL_KEY_MAP = {
    Key.space: 'Space',
    Key.enter: 'Enter',
    Key.tab: 'Tab',
    Key.backspace: 'Backspace',
    Key.delete: 'Delete',
    Key.up: 'Up',
    Key.down: 'Down',
    Key.left: 'Left',
    Key.right: 'Right',
    Key.esc: 'Escape',
    Key.f1: 'F1', Key.f2: 'F2', Key.f3: 'F3', Key.f4: 'F4',
    Key.f5: 'F5', Key.f6: 'F6', Key.f7: 'F7', Key.f8: 'F8',
    Key.f9: 'F9', Key.f10: 'F10', Key.f11: 'F11', Key.f12: 'F12',
    Key.home: 'Home', Key.end: 'End',
    Key.page_up: 'PageUp', Key.page_down: 'PageDown',
    Key.insert: 'Insert',
    Key.num_lock: 'NumLock',
    Key.caps_lock: 'CapsLock',
}

# When NumLock is OFF, numpad keys send navigation VK codes.
# Navigation cluster keys have the "extended" flag set; numpad keys don't.
# So: if extended=False and key is one of these → it's actually a numpad key.
_NUMPAD_FROM_NAV = {
    Key.end:       'Num1',
    Key.down:      'Num2',
    Key.page_down: 'Num3',
    Key.left:      'Num4',
    Key.right:     'Num6',
    Key.home:      'Num7',
    Key.up:        'Num8',
    Key.page_up:   'Num9',
    Key.insert:    'Num0',
    Key.delete:    'Num.',
}

# Raw VK → numpad name (NumLock ON, no modifier held).
_VK_TO_NUMPAD = {
    0x60: 'Num0', 0x61: 'Num1', 0x62: 'Num2', 0x63: 'Num3',
    0x64: 'Num4', 0x65: 'Num5', 0x66: 'Num6', 0x67: 'Num7',
    0x68: 'Num8', 0x69: 'Num9',
    0x6E: 'Num.', 0x6F: 'Num/', 0x6A: 'Num*', 0x6D: 'Num-', 0x6B: 'Num+',
    0x0C: 'Num5',  # VK_CLEAR = Num5 with NumLock OFF
}

# When NumLock is ON but Shift/Ctrl is held Windows substitutes the nav VK
# for the numpad VK, but leaves extended=False so we can still detect it.
# Nav VK codes that map to a numpad key when extended=False.
_NAV_VK_TO_NUMPAD = {
    0x23: 'Num1',  # VK_END
    0x28: 'Num2',  # VK_DOWN
    0x22: 'Num3',  # VK_NEXT  (PageDown)
    0x25: 'Num4',  # VK_LEFT
    0x27: 'Num6',  # VK_RIGHT
    0x24: 'Num7',  # VK_HOME
    0x26: 'Num8',  # VK_UP
    0x21: 'Num9',  # VK_PRIOR (PageUp)
    0x2D: 'Num0',  # VK_INSERT
    0x2E: 'Num.',  # VK_DELETE
}

# Scan code → US QWERTY character.  Scan codes are based on PHYSICAL key
# position and never change between layouts.  This lets us detect the QWERTY
# position of a key regardless of whether the user has AZERTY, QWERTZ, etc.
# Pro Tools shortcuts are defined by QWERTY position (not by character).
_SCAN_TO_QWERTY = {
    # Number row
    0x02: '1', 0x03: '2', 0x04: '3', 0x05: '4', 0x06: '5',
    0x07: '6', 0x08: '7', 0x09: '8', 0x0A: '9', 0x0B: '0',
    0x0C: '-', 0x0D: '=',
    # Top letter row (QWERTY: Q W E R T Y U I O P [ ])
    0x10: 'Q', 0x11: 'W', 0x12: 'E', 0x13: 'R', 0x14: 'T',
    0x15: 'Y', 0x16: 'U', 0x17: 'I', 0x18: 'O', 0x19: 'P',
    0x1A: '[', 0x1B: ']',
    # Home row (QWERTY: A S D F G H J K L ; ')
    0x1E: 'A', 0x1F: 'S', 0x20: 'D', 0x21: 'F', 0x22: 'G',
    0x23: 'H', 0x24: 'J', 0x25: 'K', 0x26: 'L',
    0x27: ';', 0x28: "'",
    0x29: '`', 0x2B: '\\',
    # Bottom row (QWERTY: Z X C V B N M , . /)
    0x2C: 'Z', 0x2D: 'X', 0x2E: 'C', 0x2F: 'V', 0x30: 'B',
    0x31: 'N', 0x32: 'M',
    0x33: ',', 0x34: '.', 0x35: '/',
    # Space
    0x39: 'Space',
}


def name_is_modifier(key):
    """Return True if key is a modifier (Shift, Ctrl, Alt, Win)."""
    return key in MODIFIER_MAP


def key_to_name(key, extended=True):
    """Convert a pynput key to our internal name string.

    extended: Windows extended-key flag (True = from navigation cluster,
              False = from numpad when NumLock is OFF).
    """
    if key in MODIFIER_MAP:
        return MODIFIER_MAP[key]

    # Numpad detection when NumLock is OFF:
    # Navigation-cluster keys have extended=True; numpad keys have extended=False.
    if not extended and key in _NUMPAD_FROM_NAV:
        return _NUMPAD_FROM_NAV[key]

    if key in SPECIAL_KEY_MAP:
        return SPECIAL_KEY_MAP[key]

    if isinstance(key, KeyCode):
        if key.vk is not None:
            # Numpad 0-9 (NumLock ON)
            if 0x60 <= key.vk <= 0x69:
                return f'Num{key.vk - 0x60}'
            # Numpad operators
            if key.vk == 0x6E: return 'Num.'
            if key.vk == 0x6F: return 'Num/'
            if key.vk == 0x6A: return 'Num*'
            if key.vk == 0x6D: return 'Num-'
            if key.vk == 0x6B: return 'Num+'
            # Numpad 5 with NumLock OFF sends VK_CLEAR (0x0C)
            if key.vk == 0x0C: return 'Num5'
        # Fallback for keys not resolved by _win32_filter scan code map
        if key.char is not None and key.char.isprintable() and len(key.char) == 1:
            return key.char.upper()
        if key.vk is not None:
            mapped = _user32.MapVirtualKeyW(key.vk, 2)  # MAPVK_VK_TO_CHAR
            if mapped > 0:
                ch = chr(mapped & 0x7FFFFFFF)  # strip dead-key high bit
                if ch.isprintable():
                    return ch.upper()
    return None


class KeyboardHandler(BaseKeyboardHandler):
    """Global keyboard listener that tracks pressed keys and detects shortcut combos."""

    def __init__(self):
        self.pressed_modifiers = set()
        self.pressed_keys = set()
        self.events = deque(maxlen=100)
        self.lock = threading.Lock()
        self.listener = None
        self._running = False
        self._last_combo = None
        self._combo_time = 0.0
        # Extended-key flag from the latest win32 hook event (set before on_press)
        self._current_extended = True
        # Key name pre-resolved from raw vkCode in _win32_filter (None = use normal path)
        self._current_key_name: str | None = None
        # Whether the current event was injected by Windows (e.g. fake Shift around numpad)
        self._current_injected = False
        # Win key suppression hook (separate from pynput)
        self._win_hook = None
        self._win_hook_cb = None
        self._game_hwnd = 0

    # ------------------------------------------------------------------
    # Win key suppression via a separate WH_KEYBOARD_LL hook.
    # pynput's win32_event_filter cannot suppress events when suppress=False,
    # so we install our own low-level hook that intercepts Win key before
    # both pynput and Windows see it.  We manually update pressed_modifiers
    # from the hook callback so the game still detects Win-based shortcuts.
    # Must be called from the main thread (the one running pygame's event
    # loop), because the hook callback is dispatched during message pumping.
    # ------------------------------------------------------------------

    def start_win_suppression(self, game_hwnd):
        """Install a low-level keyboard hook that suppresses Win key when
        the game window is focused.  Call from the main thread."""
        self._game_hwnd = game_hwnd

        def _hook_proc(nCode, wParam, lParam):
            if nCode >= 0:
                data = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT))
                vk = data.contents.vkCode
                # Cache the foreground window once per event — both Win and Tab
                # paths need it, and the call isn't free.
                game_focused = (
                    self._game_hwnd
                    and _user32.GetForegroundWindow() == self._game_hwnd
                )
                if vk in _WIN_VK_SET and game_focused:
                    is_down = wParam in (_WM_KEYDOWN, _WM_SYSKEYDOWN)
                    with self.lock:
                        if is_down:
                            self.pressed_modifiers.add('Win')
                        else:
                            self.pressed_modifiers.discard('Win')
                    return 1  # Suppress — don't pass to next hook / OS

                # Alt+Tab / Ctrl+Alt+Tab suppression: Windows steals focus when
                # Tab arrives while Alt is held. Swallow Tab and update our state
                # ourselves so the shortcut still registers in-game.
                # GetAsyncKeyState reads physical key state synchronously, side-
                # stepping the race with pynput's listener thread.
                if vk == _VK_TAB and game_focused:
                    alt_down = bool(_user32.GetAsyncKeyState(_VK_MENU) & 0x8000)
                    if alt_down:
                        is_down = wParam in (_WM_KEYDOWN, _WM_SYSKEYDOWN)
                        is_up = wParam in (_WM_KEYUP, _WM_SYSKEYUP)
                        now = time.time()
                        with self.lock:
                            if is_down:
                                self.pressed_keys.add('Tab')
                                combo = frozenset(self.pressed_modifiers | {'Tab'})
                                self._last_combo = combo
                                self._combo_time = now
                                self.events.append((now, 'combo', combo))
                            elif is_up:
                                self.pressed_keys.discard('Tab')
                        return 1
            return _user32.CallNextHookEx(0, nCode, wParam, lParam)

        self._win_hook_cb = _HOOKPROC(_hook_proc)  # prevent GC
        hmod = _kernel32.GetModuleHandleW(None)
        cb_ptr = ctypes.cast(self._win_hook_cb, ctypes.c_void_p).value
        self._win_hook = _user32.SetWindowsHookExW(
            _WH_KEYBOARD_LL, cb_ptr, hmod, 0,
        )

    def stop_win_suppression(self):
        """Remove the Win key suppression hook."""
        if self._win_hook:
            _user32.UnhookWindowsHookEx(self._win_hook)
            self._win_hook = None
            self._win_hook_cb = None

    def start(self):
        """Start the keyboard listener thread."""
        self._running = True
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False,
            win32_event_filter=self._win32_filter,
        )
        self.listener.daemon = True
        self.listener.start()

    def _win32_filter(self, msg, data):
        """Intercept raw Windows hook events to read the extended-key flag and
        resolve numpad keys directly from the raw vkCode before pynput translates
        them.

        Why vkCode directly?
        When NumLock is ON but Shift or Ctrl is held, Windows substitutes the
        navigation VK (e.g. VK_NEXT for Num3) instead of VK_NUMPAD3.  pynput
        then reports Key.page_down, making it indistinguishable from the real
        PageDown key unless we read the extended flag *and* the vkCode here,
        before any pynput translation happens.

        KBDLLHOOKSTRUCT.flags bit 0 = extended-key:
          1 = navigation cluster / right-side modifiers
          0 = numpad or main keyboard (no extended prefix)
        """
        extended = bool(data.flags & 0x01)
        self._current_extended = extended
        vk = data.vkCode
        sc = data.scanCode

        # Fake Shift detection (NumLock ON + Shift held + numpad key pressed):
        # Windows generates a synthetic Shift-up before the numpad key and a
        # synthetic Shift-down after.  These are NOT marked LLKHF_INJECTED —
        # they come from the keyboard driver itself.
        # Real Left Shift  → scanCode == 0x2A
        # Real Right Shift → scanCode == 0x36
        # Fake Shift       → scanCode == 0x22A (driver-internal E0-prefixed scan)
        # Detected by: VK is a Shift key AND scan code is not a real shift scan.
        _SHIFT_VKS = {0x10, 0xA0, 0xA1}  # VK_SHIFT, VK_LSHIFT, VK_RSHIFT
        _REAL_SHIFT_SCANS = {0x2A, 0x36}
        self._current_injected = (vk in _SHIFT_VKS and sc not in _REAL_SHIFT_SCANS)

        if vk == 0x0D and extended:
            # Numpad Enter sends VK_RETURN with the extended flag set (E0 prefix),
            # while the main keyboard Return has extended=False. Distinguish them.
            self._current_key_name = 'Num Enter'
        elif vk in _VK_TO_NUMPAD:
            # Numpad VK codes are unambiguous (NumLock ON, no modifier override)
            self._current_key_name = _VK_TO_NUMPAD[vk]
        elif not extended and vk in _NAV_VK_TO_NUMPAD:
            # Nav VK with extended=False → numpad key (NumLock OFF, or Shift/Ctrl
            # held with NumLock ON)
            self._current_key_name = _NAV_VK_TO_NUMPAD[vk]
        elif sc in _SCAN_TO_QWERTY:
            # Map physical key position to its QWERTY character.
            # This ensures AZERTY "Q" (scan 0x1E) → 'A' (QWERTY position),
            # matching Pro Tools' QWERTY-based shortcut definitions.
            self._current_key_name = _SCAN_TO_QWERTY[sc]
        else:
            self._current_key_name = None

        return True  # Don't suppress

    def stop(self):
        self._running = False
        if self.listener:
            self.listener.stop()
            self.listener = None

    def _on_press(self, key, injected=False):
        if not self._running:
            return
        # Drop Windows-injected modifier events (fake Shift-up/down around numpad keys).
        # Use pynput's own injected flag (most reliable) with our flag as fallback.
        if (injected or self._current_injected) and name_is_modifier(key):
            return
        # Prefer the name pre-resolved from raw vkCode (handles numpad + modifier)
        if self._current_key_name is not None:
            name = self._current_key_name
        else:
            name = key_to_name(key, extended=self._current_extended)
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

    def _on_release(self, key, injected=False):
        if not self._running:
            return
        # Drop Windows-injected modifier events (fake Shift-up/down around numpad keys)
        if (injected or self._current_injected) and name_is_modifier(key):
            return
        if self._current_key_name is not None:
            name = self._current_key_name
        else:
            name = key_to_name(key, extended=self._current_extended)
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

    def poll_events(self):
        with self.lock:
            events = list(self.events)
            self.events.clear()
            return events

    def check_combo_v2(self, detect_options):
        """Check if the last combo matches any of the acceptable frozensets.

        detect_options: list of frozensets from loader._build_detect_info
        Returns True (match), False (wrong combo pressed), or None (no input yet).
        """
        combo = self.get_last_combo()
        if combo is None:
            return None
        actual = frozenset(k.upper() if len(k) == 1 else k for k in combo)
        return actual in detect_options

    def check_modifier_only(self, expected_modifiers):
        """Check if exactly the expected modifiers are held (for single_key modifier shortcuts).

        Returns True if exactly matching, False if wrong set is held, None if nothing held.
        """
        with self.lock:
            if not self.pressed_modifiers:
                return None
            return self.pressed_modifiers == expected_modifiers

    def check_modifiers_for_click(self, expected_modifiers):
        """Check if the currently held modifiers match expected (for modifier_click).

        Returns True if exactly matching, False otherwise.
        """
        with self.lock:
            actual = frozenset(self.pressed_modifiers)
            return actual == expected_modifiers

    def peek_last_combo(self):
        """Return the last combo WITHOUT consuming it."""
        with self.lock:
            if self._last_combo is None:
                return None
            return frozenset(
                k.upper() if len(k) == 1 else k for k in self._last_combo
            )

    def consume_last_combo(self):
        """Consume and discard the last combo."""
        with self.lock:
            self._last_combo = None

    def clear(self):
        with self.lock:
            self.pressed_modifiers.clear()
            self.pressed_keys.clear()
            self._last_combo = None
            self.events.clear()
