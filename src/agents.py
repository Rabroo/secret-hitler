"""Player agents — random and LLM-backed — plus adapters that turn a
`{player_id: PlayerAgent}` map into the engine's ChooseFn / VoteFn callbacks.

Each agent stores `last_nominate_reasoning` and `last_vote_reasoning` strings
so the dashboard renderer can show *why* the agent made its choice. For
RandomAgent these are placeholders. For LLMAgent they come from JSON-mode
responses: `{"reasoning": "...", "choice": <id> | "vote": "ja"|"nein"}`.

See specs/agent_contracts.md, specs/llm_agent.md, specs/dashboard.md.
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass, field
from typing import Optional, Protocol

from src.game import ChooseFn, DiscardFn, EnactFn, Player, VoteFn
from src.personality import Personality
from src.policies import Policy
from src.prompts import (
    discard_prompt,
    enact_prompt,
    nominate_prompt,
    retry_prompt,
    system_prompt,
    vote_prompt,
)


_VALID_VOTES = {"ja": True, "nein": False}
_RANDOM_REASONING = "(random)"
_FALLBACK_REASONING = "(LLM parse failure — random fallback)"


class PlayerAgent(Protocol):
    """A player's brain. Owns its own identity and decides per-decision."""

    last_nominate_reasoning: str
    last_vote_reasoning: str
    last_discard_reasoning: str
    last_enact_reasoning: str

    def nominate(self, eligible: list[Player]) -> Player: ...
    def vote(self, president: Player, nominee: Player) -> bool: ...
    def discard_policy(self, hand: list[Policy]) -> Policy: ...
    def enact_policy(self, hand: list[Policy]) -> Policy: ...


@dataclass
class RandomAgent:
    player: Player
    seed: Optional[int] = None
    last_nominate_reasoning: str = ""
    last_vote_reasoning: str = ""
    last_discard_reasoning: str = ""
    last_enact_reasoning: str = ""

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def nominate(self, eligible: list[Player]) -> Player:
        chosen = self._rng.choice(eligible)
        self.last_nominate_reasoning = _RANDOM_REASONING
        return chosen

    def vote(self, president: Player, nominee: Player) -> bool:
        result = self._rng.random() < 0.5
        self.last_vote_reasoning = _RANDOM_REASONING
        return result

    def discard_policy(self, hand: list[Policy]) -> Policy:
        chosen = self._rng.choice(hand)
        self.last_discard_reasoning = _RANDOM_REASONING
        return chosen

    def enact_policy(self, hand: list[Policy]) -> Policy:
        chosen = self._rng.choice(hand)
        self.last_enact_reasoning = _RANDOM_REASONING
        return chosen


@dataclass
class LLMAgent:
    player: Player
    personality: Personality
    all_players: list[Player]
    client: object  # LLMClient or compatible (FakeLLMClient in tests)
    fallback: PlayerAgent
    last_nominate_reasoning: str = ""
    last_vote_reasoning: str = ""
    last_discard_reasoning: str = ""
    last_enact_reasoning: str = ""

    # Prompts now live in src/prompts.py — easier to find and tweak.

    # --- decisions -----------------------------------------------------------

    def discard_policy(self, hand: list[Policy]) -> Policy:
        if getattr(self.client, "is_exhausted", False):
            return self._discard_fallback(hand)

        system = system_prompt(self.player, self.personality, self.all_players)
        base_user = discard_prompt(hand)
        user = base_user

        for _ in range(2):
            try:
                reply = self.client.chat(system, user, json_mode=True)
            except RuntimeError:
                return self._discard_fallback(hand)

            parsed = self._parse_indexed_reply(reply, "discard_index", len(hand))
            if parsed is not None:
                idx, reasoning = parsed
                self.last_discard_reasoning = reasoning
                return hand[idx]
            user = retry_prompt(base_user, "expected discard_index 0..2")

        print(
            f"[agent] Player {self.player.id} LLM gave invalid discards twice; "
            "falling back to random",
            file=sys.stderr,
        )
        return self._discard_fallback(hand)

    def enact_policy(self, hand: list[Policy]) -> Policy:
        if getattr(self.client, "is_exhausted", False):
            return self._enact_fallback(hand)

        system = system_prompt(self.player, self.personality, self.all_players)
        base_user = enact_prompt(hand)
        user = base_user

        for _ in range(2):
            try:
                reply = self.client.chat(system, user, json_mode=True)
            except RuntimeError:
                return self._enact_fallback(hand)

            parsed = self._parse_indexed_reply(reply, "enact_index", len(hand))
            if parsed is not None:
                idx, reasoning = parsed
                self.last_enact_reasoning = reasoning
                return hand[idx]
            user = retry_prompt(base_user, "expected enact_index 0..1")

        print(
            f"[agent] Player {self.player.id} LLM gave invalid enactions twice; "
            "falling back to random",
            file=sys.stderr,
        )
        return self._enact_fallback(hand)

    def nominate(self, eligible: list[Player]) -> Player:
        if getattr(self.client, "is_exhausted", False):
            return self._nominate_fallback(eligible)

        eligible_ids = {p.id for p in eligible}
        system = system_prompt(self.player, self.personality, self.all_players)
        base_user = nominate_prompt(eligible)
        user = base_user

        for _ in range(2):
            try:
                reply = self.client.chat(system, user, json_mode=True)
            except RuntimeError:
                return self._nominate_fallback(eligible)

            parsed = self._parse_nominate_reply(reply, eligible_ids)
            if parsed is not None:
                chosen_id, reasoning = parsed
                self.last_nominate_reasoning = reasoning
                return next(p for p in eligible if p.id == chosen_id)
            user = retry_prompt(base_user, "ineligible choice or invalid JSON")

        print(
            f"[agent] Player {self.player.id} LLM gave invalid nominations twice; "
            "falling back to random",
            file=sys.stderr,
        )
        return self._nominate_fallback(eligible)

    def vote(self, president: Player, nominee: Player) -> bool:
        if getattr(self.client, "is_exhausted", False):
            return self._vote_fallback(president, nominee)

        system = system_prompt(self.player, self.personality, self.all_players)
        base_user = vote_prompt(president, nominee)
        user = base_user

        for _ in range(2):
            try:
                reply = self.client.chat(system, user, json_mode=True)
            except RuntimeError:
                return self._vote_fallback(president, nominee)

            parsed = self._parse_vote_reply(reply)
            if parsed is not None:
                vote_value, reasoning = parsed
                self.last_vote_reasoning = reasoning
                return vote_value
            user = retry_prompt(base_user, "didn't say ja/nein or invalid JSON")

        print(
            f"[agent] Player {self.player.id} LLM gave invalid votes twice; "
            "falling back to random",
            file=sys.stderr,
        )
        return self._vote_fallback(president, nominee)

    # --- fallbacks (annotate reasoning so the dashboard explains the source) -

    def _nominate_fallback(self, eligible: list[Player]) -> Player:
        chosen = self.fallback.nominate(eligible)
        self.last_nominate_reasoning = _FALLBACK_REASONING
        return chosen

    def _vote_fallback(self, president: Player, nominee: Player) -> bool:
        result = self.fallback.vote(president, nominee)
        self.last_vote_reasoning = _FALLBACK_REASONING
        return result

    def _discard_fallback(self, hand: list[Policy]) -> Policy:
        result = self.fallback.discard_policy(hand)
        self.last_discard_reasoning = _FALLBACK_REASONING
        return result

    def _enact_fallback(self, hand: list[Policy]) -> Policy:
        result = self.fallback.enact_policy(hand)
        self.last_enact_reasoning = _FALLBACK_REASONING
        return result

    # --- parsing -------------------------------------------------------------

    @staticmethod
    def _parse_nominate_reply(
        reply: str, allowed: set[int]
    ) -> Optional[tuple[int, str]]:
        try:
            data = json.loads(reply or "")
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        choice = data.get("choice")
        if not isinstance(choice, int) or choice not in allowed:
            return None
        reasoning = data.get("reasoning", "")
        if not isinstance(reasoning, str):
            reasoning = ""
        return choice, reasoning

    @staticmethod
    def _parse_indexed_reply(
        reply: str, key: str, hand_size: int
    ) -> Optional[tuple[int, str]]:
        try:
            data = json.loads(reply or "")
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        idx = data.get(key)
        if not isinstance(idx, int) or not (0 <= idx < hand_size):
            return None
        reasoning = data.get("reasoning", "")
        if not isinstance(reasoning, str):
            reasoning = ""
        return idx, reasoning

    @staticmethod
    def _parse_vote_reply(reply: str) -> Optional[tuple[bool, str]]:
        try:
            data = json.loads(reply or "")
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        vote_raw = data.get("vote")
        if not isinstance(vote_raw, str):
            return None
        vote_token = vote_raw.strip().lower().strip(".,!\"'`* ")
        if vote_token not in _VALID_VOTES:
            return None
        reasoning = data.get("reasoning", "")
        if not isinstance(reasoning, str):
            reasoning = ""
        return _VALID_VOTES[vote_token], reasoning


# --- adapters: agents -> engine callbacks ------------------------------------


def make_choose_fn(agents: dict[int, PlayerAgent]) -> ChooseFn:
    def choose_fn(president: Player, eligible: list[Player]) -> Player:
        return agents[president.id].nominate(eligible)

    return choose_fn


def make_vote_fn(agents: dict[int, PlayerAgent]) -> VoteFn:
    def vote_fn(voter: Player, president: Player, nominee: Player) -> bool:
        return agents[voter.id].vote(president, nominee)

    return vote_fn


def make_discard_fn(agents: dict[int, PlayerAgent]) -> DiscardFn:
    def discard_fn(president: Player, hand: list[Policy]) -> Policy:
        return agents[president.id].discard_policy(hand)

    return discard_fn


def make_enact_fn(agents: dict[int, PlayerAgent]) -> EnactFn:
    def enact_fn(chancellor: Player, hand: list[Policy]) -> Policy:
        return agents[chancellor.id].enact_policy(hand)

    return enact_fn
