"""Tests for the LLM Protocol, OllamaLLM adapter, and ScriptedLLM fixture."""

import pytest
from unittest.mock import patch

from veasy_peasy import ollama_client
from veasy_peasy.llm import LLM, OllamaLLM
from fixtures.llms import ScriptedLLM


# ---------------------------------------------------------------------------
# OllamaLLM — delegation tests
# ---------------------------------------------------------------------------

def test_ollama_llm_chat_delegates():
    """OllamaLLM.chat passes model + messages + tools to ollama_client.chat_with_tools."""
    fake_response = {"message": {"role": "assistant", "content": "hi"}, "wall_time_s": 0.1}
    messages = [{"role": "user", "content": "hello"}]
    tools = [{"type": "function", "function": {"name": "foo"}}]

    with patch.object(ollama_client, "chat_with_tools", return_value=fake_response) as mock:
        llm = OllamaLLM("test-model")
        result = llm.chat(messages, tools)

    mock.assert_called_once_with("test-model", messages, tools, temperature=0.0)
    assert result is fake_response


def test_ollama_llm_generate_delegates():
    """OllamaLLM.generate passes model + prompt + temperature to ollama_client.generate."""
    fake_response = {"response": "answer", "wall_time_s": 0.05}

    with patch.object(ollama_client, "generate", return_value=fake_response) as mock:
        llm = OllamaLLM("test-model")
        result = llm.generate("some prompt", temperature=0.7)

    mock.assert_called_once_with("test-model", "some prompt", temperature=0.7)
    assert result is fake_response


def test_ollama_llm_generate_default_temperature():
    """OllamaLLM.generate defaults temperature to 0.0."""
    fake_response = {"response": "answer", "wall_time_s": 0.05}

    with patch.object(ollama_client, "generate", return_value=fake_response) as mock:
        OllamaLLM("test-model").generate("prompt")

    mock.assert_called_once_with("test-model", "prompt", temperature=0.0)


def test_ollama_llm_satisfies_protocol():
    """OllamaLLM is structurally compatible with the LLM Protocol."""
    assert isinstance(OllamaLLM("any-model"), LLM)


# ---------------------------------------------------------------------------
# ScriptedLLM — fixture behaviour
# ---------------------------------------------------------------------------

def test_scripted_llm_chat_returns_in_order():
    """ScriptedLLM.chat returns scripted responses in order."""
    r1 = {"message": {"role": "assistant", "content": "first"}, "wall_time_s": 0.0}
    r2 = {"message": {"role": "assistant", "content": "second"}, "wall_time_s": 0.0}
    llm = ScriptedLLM(chat_responses=[r1, r2])

    out1 = llm.chat([], [])
    out2 = llm.chat([], [])

    assert out1 is r1
    assert out2 is r2


def test_scripted_llm_chat_preserves_wall_time():
    """ScriptedLLM.chat returns the response unmodified, including wall_time_s."""
    r = {"message": {"role": "assistant", "content": "hi"}, "wall_time_s": 1.5}
    llm = ScriptedLLM(chat_responses=[r])
    out = llm.chat([], [])
    assert out["wall_time_s"] == 1.5


def test_scripted_llm_generate_returns_in_order():
    """ScriptedLLM.generate returns scripted responses in order."""
    llm = ScriptedLLM(generate_responses=[
        {"response": "alpha", "wall_time_s": 0.1},
        {"response": "beta", "wall_time_s": 0.2},
    ])
    assert llm.generate("p1")["response"] == "alpha"
    assert llm.generate("p2")["response"] == "beta"


def test_scripted_llm_chat_exhaustion_raises_assertion():
    """ScriptedLLM.chat raises AssertionError (not StopIteration) when scripts run out."""
    llm = ScriptedLLM(chat_responses=[
        {"message": {"role": "assistant", "content": "only one"}, "wall_time_s": 0.0},
    ])
    llm.chat([], [])  # consume the one response
    with pytest.raises(AssertionError, match="exhausted"):
        llm.chat([], [])


def test_scripted_llm_generate_exhaustion_raises_assertion():
    """ScriptedLLM.generate raises AssertionError (not StopIteration) when scripts run out."""
    llm = ScriptedLLM(generate_responses=[{"response": "only one", "wall_time_s": 0.0}])
    llm.generate("first")
    with pytest.raises(AssertionError, match="exhausted"):
        llm.generate("second")


def test_scripted_llm_empty_scripts_raise_immediately():
    """ScriptedLLM with no scripts raises AssertionError on first call."""
    llm = ScriptedLLM()
    with pytest.raises(AssertionError, match="exhausted"):
        llm.chat([], [])


def test_scripted_llm_rejects_malformed_chat_response():
    """ScriptedLLM raises AssertionError if a chat response is missing required keys."""
    with pytest.raises(AssertionError, match="chat_responses"):
        ScriptedLLM(chat_responses=[{"role": "assistant", "content": "missing wrapper"}])


def test_scripted_llm_rejects_malformed_generate_response():
    """ScriptedLLM raises AssertionError if a generate response is missing required keys."""
    with pytest.raises(AssertionError, match="generate_responses"):
        ScriptedLLM(generate_responses=[{"text": "wrong key"}])


def test_scripted_llm_satisfies_protocol():
    """ScriptedLLM is structurally compatible with the LLM Protocol."""
    assert isinstance(ScriptedLLM(), LLM)
