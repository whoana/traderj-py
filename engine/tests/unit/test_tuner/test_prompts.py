"""Tests for engine.tuner.prompts."""

import pytest

from engine.tuner.prompts import parse_llm_json


def test_parse_direct_json():
    text = '{"root_causes": ["a"], "confidence": "high"}'
    result = parse_llm_json(text)
    assert result["root_causes"] == ["a"]
    assert result["confidence"] == "high"


def test_parse_json_in_code_block():
    text = '```json\n{"approved": true, "reason": "ok"}\n```'
    result = parse_llm_json(text)
    assert result["approved"] is True


def test_parse_json_in_code_block_no_lang():
    text = '```\n{"key": "value"}\n```'
    result = parse_llm_json(text)
    assert result["key"] == "value"


def test_parse_json_with_surrounding_text():
    text = 'Here is my analysis:\n{"root_causes": ["noise"], "confidence": "low"}\nEnd.'
    result = parse_llm_json(text)
    assert result["root_causes"] == ["noise"]


def test_parse_nested_json():
    text = '{"a": {"b": [1, 2]}, "c": true}'
    result = parse_llm_json(text)
    assert result["a"]["b"] == [1, 2]


def test_parse_invalid_json_raises():
    with pytest.raises(ValueError, match="Failed to parse JSON"):
        parse_llm_json("This is not JSON at all")


def test_parse_empty_raises():
    with pytest.raises(ValueError, match="Failed to parse JSON"):
        parse_llm_json("")


def test_parse_json_with_whitespace():
    text = '  \n  {"key": 42}  \n  '
    result = parse_llm_json(text)
    assert result["key"] == 42
