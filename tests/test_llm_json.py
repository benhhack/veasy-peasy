import pytest
from veasy_peasy.llm_json import parse_llm_json


def test_bare_json_object():
    assert parse_llm_json('{"a": 1, "b": 2}') == {"a": 1, "b": 2}


def test_fenced_json_with_language_tag():
    assert parse_llm_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_fenced_json_without_language_tag():
    assert parse_llm_json('```\n{"a": 1}\n```') == {"a": 1}


def test_embedded_json_with_prose():
    assert parse_llm_json('Here is the answer: {"a": 1}. Hope that helps.') == {"a": 1}


def test_leading_trailing_whitespace():
    assert parse_llm_json('  \n {"a": 1}\n  ') == {"a": 1}


def test_nested_braces():
    assert parse_llm_json('pre {"a": {"b": 1}} post') == {"a": {"b": 1}}


def test_invalid_json_content():
    assert parse_llm_json('not json at all') is None


def test_malformed_json():
    assert parse_llm_json('{not valid}') is None


def test_empty_string():
    assert parse_llm_json('') is None


def test_whitespace_only_string():
    assert parse_llm_json('   \n\t  ') is None


def test_non_dict_top_level_array():
    assert parse_llm_json('[1, 2, 3]') is None


def test_required_keys_missing():
    assert parse_llm_json('{"a": 1, "c": 2}', required_keys=("a", "b")) is None


def test_required_keys_all_present_with_extras():
    result = parse_llm_json('{"a": 1, "b": 2, "c": 3}', required_keys=("a", "b"))
    assert result == {"a": 1, "b": 2, "c": 3}


def test_required_keys_empty_returns_dict():
    assert parse_llm_json('{"x": 99}', required_keys=()) == {"x": 99}
