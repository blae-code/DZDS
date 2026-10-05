"""Ollama client for the GM cognition loop (Gemma 4 E4B, strict JSON)."""
from __future__ import annotations

import json
import logging
import re

import httpx
from pydantic import ValidationError

from .schema import GMPayload, json_schema

log = logging.getLogger(__name__)

# Gemma 4 thinking channel markers, plus generic <think> tags from other models.
_THOUGHT = re.compile(
    r"<\|channel\>thought.*?(?:<channel\|>|<\|channel\>(?!thought)|$)|<think>.*?</think>",
    re.DOTALL,
)

SYSTEM_PROMPT = """You are the unseen Game Master of a persistent DayZ PvE world.
You receive a digest of recent telemetry and decide whether the world should react.
Rules:
- Stay diegetic: broadcasts are crackly radio chatter, rumours or intercepted transmissions.
  Never mention game mechanics, HUDs, coordinates as numbers, or that you are an AI.
- The world is at war: CDF (army remnant, holds bases and airfields) vs ChDKZ (insurgents,
  hold industry and roads), with Raiders (bandits) preying on everyone and Survivors
  (civilians) caught between. Broadcasts can be intercepted faction radio traffic,
  civilian warnings or rumours about who holds what.
- Be sparing. Returning an empty broadcast and no actions is often correct.
- At most one world action unless players are clearly idle and bored.
- Prefer a named location from the provided list over raw coords.
- Reply ONLY with JSON matching the schema."""


def strip_thoughts(text: str) -> str:
    return _THOUGHT.sub("", text).strip()


def extract_json(text: str) -> dict:
    text = strip_thoughts(text)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start:end + 1])


class OllamaGM:
    def __init__(self, url: str, model: str, timeout: float = 60.0) -> None:
        self.url, self.model = url.rstrip("/"), model
        self.client = httpx.AsyncClient(timeout=timeout)

    async def decide(self, digest: str, locations: list[str]) -> GMPayload | None:
        body = {
            "model": self.model,
            "stream": False,
            "format": json_schema(),
            "options": {"temperature": 0.8},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Known locations: {', '.join(locations)}\n\n"
                                            f"Telemetry digest:\n{digest}"},
            ],
        }
        try:
            r = await self.client.post(f"{self.url}/api/chat", json=body)
            r.raise_for_status()
            content = r.json()["message"]["content"]
            return GMPayload.model_validate(extract_json(content))
        except (httpx.HTTPError, KeyError, json.JSONDecodeError, ValidationError) as exc:
            log.warning("GM cognition failed: %s", exc)
            return None

    async def aclose(self) -> None:
        await self.client.aclose()
