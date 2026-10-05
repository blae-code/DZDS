"""The GM's structured output contract (spec §5.3) and its sanitisation.

LLM output is untrusted: unknown action targets are dropped, coordinates are resolved
from named locations or clamped to map bounds, and broadcasts are cleaned for RCON.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Whitelisted world-event targets. Add here only once the dispatcher supports them.
EventTarget = Literal["spawn_airdrop", "spawn_ai_patrol", "spawn_heli_crash", "spawn_hacked_crate"]

MAX_BROADCAST = 200


class WorldAction(BaseModel):
    type: Literal["trigger_event"] = "trigger_event"
    target: EventTarget
    location: str | None = None
    coords: tuple[float, float] | None = None
    delay_seconds: int = Field(default=30, ge=0, le=1800)


class GMPayload(BaseModel):
    narrative_broadcast: str = ""
    world_actions: list[WorldAction] = Field(default_factory=list, max_length=3)

    @field_validator("narrative_broadcast")
    @classmethod
    def clean_broadcast(cls, v: str) -> str:
        v = re.sub(r"[\x00-\x1f\x7f]", " ", v)  # no control chars / newlines into RCON
        v = re.sub(r"\s+", " ", v).strip()
        return v[:MAX_BROADCAST]

    @field_validator("world_actions", mode="before")
    @classmethod
    def drop_unknown(cls, v):  # noqa: ANN001
        """Silently drop actions whose target isn't whitelisted instead of failing the whole payload."""
        allowed = set(EventTarget.__args__)
        return [a for a in (v or []) if isinstance(a, dict) and a.get("target") in allowed]


def json_schema() -> dict:
    """Schema passed to Ollama's `format` field to constrain generation."""
    return GMPayload.model_json_schema()


def resolve_coords(action: WorldAction, locations: dict[str, list[float]],
                   bounds: tuple[float, float, float, float]) -> tuple[float, float] | None:
    """Named location wins over raw coords; result is clamped to (xmin, zmin, xmax, zmax)."""
    xy = None
    if action.location and action.location in locations:
        xy = tuple(locations[action.location][:2])
    elif action.coords:
        xy = action.coords
    if xy is None:
        return None
    xmin, zmin, xmax, zmax = bounds
    return (min(max(xy[0], xmin), xmax), min(max(xy[1], zmin), zmax))
