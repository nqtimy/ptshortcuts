"""Debug script: prints raw Windows hook data for every key event."""

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

def win32_filter(msg, data):
    WM_KEYDOWN   = 0x0100
    WM_KEYUP     = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP  = 0x0105
    direction = "DN" if msg in (WM_KEYDOWN, WM_SYSKEYDOWN) else "UP"
    extended  = bool(data.flags & 0x01)
    injected  = bool(data.flags & 0x10)
    print(f"  [{direction}] vk=0x{data.vkCode:02X}  scan=0x{data.scanCode:02X}  "
          f"flags=0x{data.flags:02X}  extended={extended}  injected={injected}")
    return True

def on_press(key, injected=False):
    print(f"    pynput press   key={key!r}  injected={injected}")

def on_release(key, injected=False):
    print(f"    pynput release key={key!r}  injected={injected}")
    if key == Key.esc:
        return False  # stop

print("Appuie sur des touches (Echap pour quitter).")
print("Teste : Ctrl+Shift+Num3, puis Ctrl+Num3+Shift")
print()

with keyboard.Listener(
    on_press=on_press,
    on_release=on_release,
    suppress=False,
    win32_event_filter=win32_filter,
) as listener:
    listener.join()
