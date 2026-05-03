"""LLM Protocol and OllamaLLM adapter.

Provides a swappable seam so the engine and matcher depend on a clean
interface rather than on ollama_client directly.
"""

from typing import Protocol, TypedDict, runtime_checkable

from veasy_peasy import ollama_client


class ChatResponse(TypedDict):
    message: dict
    wall_time_s: float
    # Pass-through fields like eval_count ride along; TypedDict doesn't reject extras at runtime.


class GenerateResponse(TypedDict):
    response: str
    wall_time_s: float


@runtime_checkable
class LLM(Protocol):
    model_name: str

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResponse:
        """Call the model with tool definitions.

        Tool-call chat is always deterministic (temperature=0.0). Sampling is
        only exposed on `generate`.
        """
        ...

    def generate(self, prompt: str, temperature: float = 0.0) -> GenerateResponse:
        """Generate a completion."""
        ...


class OllamaLLM:
    def __init__(self, model: str) -> None:
        self.model_name = model

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResponse:
        # Tool-call chat is always deterministic (temperature=0.0); sampling lives on generate.
        return ollama_client.chat_with_tools(self.model_name, messages, tools, temperature=0.0)

    def generate(self, prompt: str, temperature: float = 0.0) -> GenerateResponse:
        return ollama_client.generate(self.model_name, prompt, temperature=temperature)
