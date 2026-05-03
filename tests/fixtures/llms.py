"""Test fixtures for LLM implementations."""

from veasy_peasy.llm import ChatResponse, GenerateResponse


class ScriptedLLM:
    """A test fake that returns scripted responses in order.

    Each scripted response must be pre-shaped to match the LLM Protocol's
    return contract:
      - chat_responses: each entry must have keys 'message' (dict) and 'wall_time_s' (float)
      - generate_responses: each entry must have keys 'response' (str) and 'wall_time_s' (float)

    Raises AssertionError (not StopIteration) if more responses are requested
    than were scripted, so test failures point to the right place.
    """

    def __init__(
        self,
        chat_responses: list[ChatResponse] | None = None,
        generate_responses: list[GenerateResponse] | None = None,
    ) -> None:
        chat_responses = list(chat_responses or [])
        generate_responses = list(generate_responses or [])
        for i, r in enumerate(chat_responses):
            assert isinstance(r, dict) and isinstance(r.get("message"), dict) and isinstance(
                r.get("wall_time_s"), (int, float)
            ), (
                f"chat_responses[{i}] must be a dict with 'message' (dict) and "
                f"'wall_time_s' (float); got {r!r}"
            )
        for i, r in enumerate(generate_responses):
            assert isinstance(r, dict) and isinstance(r.get("response"), str) and isinstance(
                r.get("wall_time_s"), (int, float)
            ), (
                f"generate_responses[{i}] must be a dict with 'response' (str) and "
                f"'wall_time_s' (float); got {r!r}"
            )
        self._chat = chat_responses
        self._generate = generate_responses
        self._chat_idx = 0
        self._generate_idx = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResponse:
        if self._chat_idx >= len(self._chat):
            raise AssertionError(
                f"ScriptedLLM.chat exhausted after {self._chat_idx} call(s); "
                "add more chat_responses to the fixture"
            )
        resp = self._chat[self._chat_idx]
        self._chat_idx += 1
        return resp

    def generate(self, prompt: str, temperature: float = 0.0) -> GenerateResponse:
        if self._generate_idx >= len(self._generate):
            raise AssertionError(
                f"ScriptedLLM.generate exhausted after {self._generate_idx} call(s); "
                "add more generate_responses to the fixture"
            )
        resp = self._generate[self._generate_idx]
        self._generate_idx += 1
        return resp
