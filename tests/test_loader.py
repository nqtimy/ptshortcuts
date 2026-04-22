"""Tests for game/loader.py — key normalization, validation, and detection info."""

import pytest

from game.loader import (
    _normalize_one_key,
    _validate_shortcut,
    _build_detect_info,
    _build_sequence_detect_info,
)


# ---------------------------------------------------------------------------
# _normalize_one_key
# ---------------------------------------------------------------------------

class TestNormalizeOneKey:
    def test_anydigit_expands_all(self):
        result = _normalize_one_key('AnyDigit')
        assert '0' in result and '9' in result
        assert 'Num0' in result and 'Num9' in result
        assert len(result) == 20

    def test_start_maps_to_win(self):
        assert _normalize_one_key('Start') == ['Win']

    def test_numpad_range(self):
        assert _normalize_one_key('Numpad 0-5') == ['Num0', 'Num1', 'Num2', 'Num3', 'Num4', 'Num5']

    def test_numpad_single(self):
        assert _normalize_one_key('Numpad 7') == ['Num7']

    def test_arrow_alternatives(self):
        assert _normalize_one_key('Up/Down Arrow') == ['Up', 'Down']
        assert _normalize_one_key('Left/Right Arrow') == ['Left', 'Right']

    def test_arrow_single(self):
        assert _normalize_one_key('Up Arrow') == ['Up']
        assert _normalize_one_key('Down Arrow') == ['Down']

    def test_function_key_range(self):
        assert _normalize_one_key('F1-F4') == ['F1', 'F2', 'F3', 'F4']

    def test_bare_number_range(self):
        assert _normalize_one_key('1-9') == ['1', '2', '3', '4', '5', '6', '7', '8', '9']

    def test_slash_alternatives(self):
        result = _normalize_one_key('Num+/Num-')
        assert result == ['Num+', 'Num-']

    def test_num_slash_no_alternative(self):
        # "Num/" has only one non-empty part after split → not an alternative
        result = _normalize_one_key('Num/')
        assert result == ['Num/']

    def test_bare_slash(self):
        result = _normalize_one_key('/')
        assert result == ['/']

    def test_single_char_uppercase(self):
        assert _normalize_one_key('a') == ['A']
        assert _normalize_one_key('z') == ['Z']

    def test_passthrough(self):
        assert _normalize_one_key('Enter') == ['Enter']
        assert _normalize_one_key('Space') == ['Space']
        assert _normalize_one_key('Tab') == ['Tab']

    def test_click_passthrough(self):
        assert _normalize_one_key('Click') == ['Click']
        assert _normalize_one_key('Right-Click') == ['Right-Click']
        assert _normalize_one_key('Double-Click') == ['Double-Click']


# ---------------------------------------------------------------------------
# _validate_shortcut
# ---------------------------------------------------------------------------

class TestValidateShortcut:
    def _valid(self):
        return {
            'command_name': 'Test Command',
            'keys_win': ['Ctrl', 'A'],
            'input_type': 'key_combo',
        }

    def test_valid_shortcut_returns_none(self):
        assert _validate_shortcut(self._valid(), 'test.json', 'Cat') is None

    def test_missing_command_name(self):
        sc = self._valid()
        del sc['command_name']
        assert _validate_shortcut(sc, 'test.json', 'Cat') is not None

    def test_empty_command_name(self):
        sc = self._valid()
        sc['command_name'] = '   '
        assert _validate_shortcut(sc, 'test.json', 'Cat') is not None

    def test_missing_keys_win(self):
        sc = self._valid()
        del sc['keys_win']
        assert _validate_shortcut(sc, 'test.json', 'Cat') is not None

    def test_empty_keys_win(self):
        sc = self._valid()
        sc['keys_win'] = []
        assert _validate_shortcut(sc, 'test.json', 'Cat') is not None

    def test_keys_win_not_list(self):
        sc = self._valid()
        sc['keys_win'] = 'Ctrl+A'
        assert _validate_shortcut(sc, 'test.json', 'Cat') is not None

    def test_invalid_input_type(self):
        sc = self._valid()
        sc['input_type'] = 'magic'
        assert _validate_shortcut(sc, 'test.json', 'Cat') is not None

    def test_valid_all_input_types(self):
        for itype in ('key_combo', 'modifier_click', 'single_key'):
            sc = self._valid()
            sc['input_type'] = itype
            assert _validate_shortcut(sc, 'test.json', 'Cat') is None

    def test_key_sequence_valid(self):
        sc = {
            'command_name': 'Seq Command',
            'keys_win': [['Ctrl', 'Alt', '1'], ['B']],
            'input_type': 'key_sequence',
        }
        assert _validate_shortcut(sc, 'test.json', 'Cat') is None

    def test_key_sequence_flat_list_is_invalid(self):
        sc = {
            'command_name': 'Seq Command',
            'keys_win': ['Ctrl', 'Alt', '1', 'B'],
            'input_type': 'key_sequence',
        }
        assert _validate_shortcut(sc, 'test.json', 'Cat') is not None

    def test_legacy_keys_field_accepted(self):
        sc = {
            'command_name': 'Legacy',
            'keys': ['Ctrl', 'Z'],
            'input_type': 'key_combo',
        }
        assert _validate_shortcut(sc, 'test.json', 'Cat') is None

    def test_error_message_contains_filename(self):
        sc = self._valid()
        del sc['command_name']
        err = _validate_shortcut(sc, 'myfile.json', 'MyCat')
        assert 'myfile.json' in err


# ---------------------------------------------------------------------------
# _build_detect_info
# ---------------------------------------------------------------------------

class TestBuildDetectInfo:
    def test_simple_combo(self):
        info = _build_detect_info(['Ctrl', 'A'], 'key_combo')
        assert info['_detect_modifiers'] == frozenset({'Ctrl'})
        assert frozenset({'Ctrl', 'A'}) in info['_detect_key_options']

    def test_modifier_only(self):
        info = _build_detect_info(['Ctrl', 'Shift'], 'key_combo')
        assert info['_detect_modifiers'] == frozenset({'Ctrl', 'Shift'})
        assert frozenset({'Ctrl', 'Shift'}) in info['_detect_key_options']

    def test_alternatives_expand(self):
        # Num+/Num- should create two options
        info = _build_detect_info(['Shift', 'Num+/Num-'], 'key_combo')
        options = info['_detect_key_options']
        assert frozenset({'Shift', 'Num+'}) in options
        assert frozenset({'Shift', 'Num-'}) in options

    def test_click_detected(self):
        info = _build_detect_info(['Ctrl', 'Click'], 'modifier_click')
        assert info['_detect_click'] == 'left'
        assert info['_detect_modifiers'] == frozenset({'Ctrl'})

    def test_right_click_detected(self):
        info = _build_detect_info(['Right-Click'], 'modifier_click')
        assert info['_detect_click'] == 'right'

    def test_double_click_detected(self):
        info = _build_detect_info(['Ctrl', 'Double-Click'], 'modifier_click')
        assert info['_detect_click'] == 'double'
        assert info['_detect_modifiers'] == frozenset({'Ctrl'})
        # Double-Click should not appear in key options
        for opt in info['_detect_key_options']:
            assert 'Double-Click' not in opt

    def test_input_type_stored(self):
        info = _build_detect_info(['Ctrl', 'S'], 'key_combo')
        assert info['_detect_input_type'] == 'key_combo'

    def test_start_maps_to_win(self):
        info = _build_detect_info(['Start', 'A'], 'key_combo')
        assert 'Win' in info['_detect_modifiers']


# ---------------------------------------------------------------------------
# _build_sequence_detect_info
# ---------------------------------------------------------------------------

class TestBuildSequenceDetectInfo:
    def test_two_step_sequence(self):
        info = _build_sequence_detect_info([['Ctrl', 'Alt', '1'], ['B']])
        assert info['_detect_input_type'] == 'key_sequence'
        steps = info['_detect_steps']
        assert len(steps) == 2
        assert frozenset({'Ctrl', 'Alt', '1'}) in steps[0]['_detect_key_options']
        assert frozenset({'B'}) in steps[1]['_detect_key_options']

    def test_single_step(self):
        info = _build_sequence_detect_info([['Ctrl', 'Z']])
        assert len(info['_detect_steps']) == 1
