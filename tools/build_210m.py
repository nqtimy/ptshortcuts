"""Parse 210M shortcuts from .txt and match with CSV export to build 210M.json."""

import csv
import json
import re
import sys


def parse_txt(path):
    """Extract shortcuts from the .txt file, organized by lesson."""
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    # Find the shortcuts section
    start = text.find("Lesson 1:")
    if start == -1:
        print("ERROR: Could not find 'Lesson 1:' in txt file")
        sys.exit(1)

    # Cut off the non-shortcut content at end
    end_markers = ["Ok c'est parti", "Ok c'est parti"]
    for marker in end_markers:
        idx = text.find(marker, start)
        if idx != -1:
            text = text[:idx]
            break

    text = text[start:]

    # Split by lessons
    lesson_pattern = re.compile(r'Lesson\s+(\d+)\s*:', re.IGNORECASE)
    lessons = {}
    parts = lesson_pattern.split(text)
    # parts = ['', '1', '<lesson1 content>', '2', '<lesson2 content>', ...]

    for i in range(1, len(parts) - 1, 2):
        lesson_num = int(parts[i])
        content = parts[i + 1]
        shortcuts = parse_lesson_shortcuts(content)
        lessons[lesson_num] = shortcuts

    return lessons


def parse_lesson_shortcuts(content):
    """Parse individual shortcuts from a lesson's text content."""
    shortcuts = []
    # Split by lines, combine multi-line sentences
    lines = [l.strip() for l in content.split('\n')]
    lines = [l.lstrip('* ').strip() for l in lines]  # Remove bullet markers

    sentences = []
    current = ""
    for line in lines:
        if not line:
            if current:
                sentences.append(current)
                current = ""
            continue
        if current:
            current += " " + line
        else:
            current = line
    if current:
        sentences.append(current)

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # Must start with Press or Hold
        if not (sentence.startswith("Press") or sentence.startswith("Hold")):
            continue

        sc = parse_shortcut_sentence(sentence)
        if sc:
            shortcuts.append(sc)

    return shortcuts


def parse_shortcut_sentence(sentence):
    """Parse a single shortcut sentence into structured data."""
    result = {
        'context': sentence,
        'has_click': False,
        'has_drag': False,
        'keys_mac': [],
        'keys_win': [],
        'command_name': '',
    }

    # Detect click/drag actions
    click_words = ['while clicking', 'while right-clicking', 'while Record-enabling',
                   'while selecting', 'while clicking on']
    drag_words = ['while dragging', 'while moving', 'while using the Trim tool',
                  'when importing']
    for w in click_words:
        if w in sentence.lower():
            result['has_click'] = True
            break
    for w in drag_words:
        if w in sentence.lower():
            result['has_click'] = True  # We treat drag as click for game purposes
            break

    # Extract command name: text after "to " near the end
    to_match = re.search(r'\bto\s+(.+?)\.?\s*$', sentence)
    if to_match:
        cmd = to_match.group(1).strip().rstrip('.')
        # Shorten it
        cmd = cmd[:80]
        result['command_name'] = cmd
    else:
        # Fallback: use the full sentence shortened
        result['command_name'] = sentence[:60]

    # Extract Mac and Win keys
    # Pattern: "Press/Hold X (Mac) or Y (Windows)"
    mac_win_pattern = re.compile(
        r'(?:Press|Hold)\s+(.+?)\s*\(Mac\)\s*or\s+(.+?)\s*\(Windows\)',
        re.IGNORECASE
    )
    match = mac_win_pattern.search(sentence)
    if match:
        mac_raw = match.group(1).strip()
        win_raw = match.group(2).strip()
        result['keys_mac'] = normalize_keys(mac_raw)
        result['keys_win'] = normalize_keys(win_raw)
    else:
        # Try pattern without (Mac)/(Windows) - same keys on both
        # "Press Tab to...", "Press Shift+S to...", "Press the [7] key on the numeric keypad"
        key_match = re.match(
            r'(?:Press|Hold)\s+(?:the\s+)?(.+?)(?:\s+(?:to|in|while|with|key|keys|on|when)\b)',
            sentence,
            re.IGNORECASE
        )
        if key_match:
            raw = key_match.group(1).strip()
            # Clean up
            raw = re.sub(r'\s*\(Mac\)', '', raw)
            raw = re.sub(r'\s*\(Windows\)', '', raw)
            raw = re.sub(r'\s*or\s+.*', '', raw)
            keys = normalize_keys(raw)
            result['keys_mac'] = keys
            result['keys_win'] = keys

    if result['has_click']:
        if 'Click' not in result['keys_mac']:
            result['keys_mac'].append('Click')
        if 'Click' not in result['keys_win']:
            result['keys_win'].append('Click')

    return result


def normalize_keys(raw):
    """Convert raw key string to list of normalized key names."""
    # Remove brackets around numpad keys: [7] -> Numpad 7
    raw = re.sub(r'\[(\d+)\]', r'Numpad \1', raw)
    # Handle "numeric keypad" mentions
    raw = re.sub(r'on the numeric keypad', '', raw)

    # Split by +
    parts = [p.strip() for p in raw.split('+')]

    keys = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Normalize key names
        k = normalize_key_name(p)
        if k:
            keys.append(k)
    return keys


def normalize_key_name(name):
    """Normalize a single key name."""
    name = name.strip().strip('()')

    mapping = {
        'Command': 'Command',
        'Cmd': 'Command',
        'Control': 'Control',
        'Ctrl': 'Ctrl',
        'CTRL': 'Ctrl',
        'Option': 'Option',
        'Alt': 'Alt',
        'Shift': 'Shift',
        'Start': 'Start',
        'Return': 'Return',
        'Enter': 'Enter',
        'Tab': 'Tab',
        'Space': 'Space',
        'Backspace': 'Backspace',
        'Delete': 'Delete',
        'Escape': 'Escape',
        'Up Arrow': 'Up Arrow',
        'Down Arrow': 'Down Arrow',
        'Left Arrow': 'Left Arrow',
        'Right Arrow': 'Right Arrow',
        'Up/Down Arrow': 'Up/Down Arrow',
        'Left/Right Arrow': 'Left/Right Arrow',
    }

    if name in mapping:
        return mapping[name]

    # Function keys
    if re.match(r'^F\d+$', name):
        return name

    # Numpad keys
    numpad_match = re.match(r'^Numpad\s*(\S+)$', name, re.IGNORECASE)
    if numpad_match:
        return f"Numpad {numpad_match.group(1)}"

    # Single characters/symbols
    if len(name) == 1 or name in ('/', '\\', ',', '.', ';', '=', '-', '0', '3', '8'):
        return name

    # Numbers with (zero) etc
    zero_match = re.match(r'^(\d+)\s*\(.*\)$', name)
    if zero_match:
        return zero_match.group(1)

    # Arrow keys written differently
    if 'arrow' in name.lower():
        if 'up' in name.lower() and 'down' in name.lower():
            return 'Up/Down Arrow'
        if 'left' in name.lower() and 'right' in name.lower():
            return 'Left/Right Arrow'
        if 'up' in name.lower():
            return 'Up Arrow'
        if 'down' in name.lower():
            return 'Down Arrow'
        if 'left' in name.lower():
            return 'Left Arrow'
        if 'right' in name.lower():
            return 'Right Arrow'

    # Special: P and ; pattern
    if name in ('P and ; (semi-colon)', 'P and ;'):
        return 'P/;'

    # Semicolon variations
    if 'semicolon' in name.lower() or name == ';':
        return ';'

    # Clean up any remaining text
    cleaned = re.sub(r'\s*\(.*?\)', '', name).strip()
    if cleaned:
        return cleaned

    return name


def parse_csv(path):
    """Parse the CSV export into a lookup by Mac keys and by Windows keys."""
    entries = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)  # Tags, Mac, Windows, Command
        for row in reader:
            if len(row) < 4:
                continue
            tags, mac, win, command = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip()
            if not mac and not win:
                continue
            entries.append({
                'tags': tags,
                'mac': mac,
                'win': win,
                'command': command,
            })
    return entries


def csv_key_to_normalized(csv_key_str):
    """Normalize a CSV key string like 'Ctrl + Shift + C' to a sorted tuple for comparison."""
    if not csv_key_str:
        return ()
    parts = [p.strip() for p in csv_key_str.split('+')]
    return tuple(sorted(p.strip() for p in parts if p.strip()))


def match_csv(txt_keys_mac, txt_keys_win, csv_entries):
    """Try to find a CSV entry matching the given keys."""
    # Build a comparable key from txt
    mac_set = set(txt_keys_mac) - {'Click'}
    win_set = set(txt_keys_win) - {'Click'}

    if not mac_set and not win_set:
        return None

    for entry in csv_entries:
        csv_mac_parts = set(p.strip() for p in entry['mac'].split('+')) if entry['mac'] else set()
        csv_win_parts = set(p.strip() for p in entry['win'].split('+')) if entry['win'] else set()

        # Try matching Windows keys first (more reliable for AZERTY)
        if win_set and csv_win_parts:
            if win_set == csv_win_parts:
                return entry

        # Try Mac keys
        if mac_set and csv_mac_parts:
            if mac_set == csv_mac_parts:
                return entry

    return None


def calc_difficulty(keys):
    """Calculate difficulty based on number of modifiers and click."""
    modifiers = {'Command', 'Control', 'Ctrl', 'Option', 'Alt', 'Shift', 'Start'}
    has_click = 'Click' in keys
    mod_count = sum(1 for k in keys if k in modifiers)
    non_mod_non_click = [k for k in keys if k not in modifiers and k != 'Click']

    if has_click:
        if mod_count >= 2:
            return 3
        return 2
    if mod_count >= 3:
        return 3
    if mod_count >= 2:
        return 2
    return 1


def build_json(lessons, csv_entries):
    """Build the final 210M.json structure."""
    categories = []
    seen_keys = set()  # Track duplicates by win keys

    for lesson_num in sorted(lessons.keys()):
        shortcuts_data = []
        for sc in lessons[lesson_num]:
            # Dedup: skip if we've seen the same win keys
            win_key_tuple = tuple(sorted(sc['keys_win']))
            if win_key_tuple in seen_keys and win_key_tuple != ():
                continue
            seen_keys.add(win_key_tuple)

            # Try CSV match for exact key notation
            csv_match = match_csv(sc['keys_mac'], sc['keys_win'], csv_entries)

            if csv_match and not sc['has_click']:
                # Use CSV's exact keys
                keys_mac_str = csv_match['mac']
                keys_win_str = csv_match['win']
                keys_mac = [p.strip() for p in keys_mac_str.split('+')]
                keys_win = [p.strip() for p in keys_win_str.split('+')]
            else:
                keys_mac = sc['keys_mac']
                keys_win = sc['keys_win']

            difficulty = calc_difficulty(keys_win if keys_win else keys_mac)

            # Determine input type
            if sc['has_click']:
                input_type = "modifier_click"
            elif len([k for k in keys_win if k not in {'Ctrl', 'Alt', 'Shift', 'Start', 'Command', 'Control', 'Option'}]) == 0:
                input_type = "modifier_only"
            elif len(keys_win) == 1:
                input_type = "single_key"
            else:
                input_type = "key_combo"

            shortcut = {
                'command_name': sc['command_name'],
                'context': sc['context'],
                'keys_mac': keys_mac,
                'keys_win': keys_win,
                'difficulty': difficulty,
                'input_type': input_type,
                'weight': max(1, 11 - difficulty * 3),
            }
            shortcuts_data.append(shortcut)

        if shortcuts_data:
            categories.append({
                'name': f'Lesson {lesson_num}',
                'shortcuts': shortcuts_data,
            })

    return {
        'certification': '210M',
        'categories': categories,
    }


def main():
    txt_path = r"C:\Users\peter\Downloads\Crée un jeu Python exportable en .txt"
    csv_path = r"C:\Users\peter\Desktop\Keyboard Shortcuts.csv"
    out_path = r"C:\Users\peter\Documents\PTShortcuts\shortcuts\210M.json"

    print("Parsing .txt file...")
    lessons = parse_txt(txt_path)
    for num, shortcuts in sorted(lessons.items()):
        print(f"  Lesson {num}: {len(shortcuts)} shortcuts")

    print(f"\nParsing CSV file...")
    csv_entries = parse_csv(csv_path)
    print(f"  {len(csv_entries)} entries with shortcuts")

    print(f"\nBuilding JSON...")
    data = build_json(lessons, csv_entries)

    total = sum(len(cat['shortcuts']) for cat in data['categories'])
    print(f"  {len(data['categories'])} categories, {total} shortcuts total")

    # Show details
    for cat in data['categories']:
        print(f"\n  {cat['name']}:")
        for sc in cat['shortcuts']:
            csv_match = '(CSV)' if sc['input_type'] != 'modifier_click' else '(TXT+Click)'
            mac_str = ' + '.join(sc['keys_mac'])
            win_str = ' + '.join(sc['keys_win'])
            print(f"    [{sc['difficulty']}] {sc['command_name'][:50]}")
            print(f"        Mac: {mac_str}  |  Win: {win_str}  {csv_match}")

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nWritten to {out_path}")


if __name__ == '__main__':
    main()
