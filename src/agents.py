"""Player agents — random and LLM-backed — plus adapters that turn a
`{player_id: PlayerAgent}` map into the engine's ChooseFn / VoteFn callbacks.

See specs/agent_contracts.md and specs/llm_agent.md.
"""

from __future__ import annotations

import random
import re
import sys
from dataclasses import dataclass
from typing import Optional, Protocol

from src.game import ChooseFn, Player, VoteFn
from src.personality import Personality


_VALID_VOTES = {"ja": True, "nein": False}
_INTEGER_RE = re.compile(r"\d+")


class PlayerAgent(Protocol):
    """A player's brain. Owns its own identity and decides per-decision."""

    def nominate(self, eligible: list[Player]) -> Player: ...
    def vote(self, president: Player, nominee: Player) -> bool: ...


@dataclass
class RandomAgent:
    player: Player
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def nominate(self, eligible: list[Player]) -> Player:
        return self._rng.choice(eligible)

    def vote(self, president: Player, nominee: Player) -> bool:
        return self._rng.random() < 0.5


@dataclass
class LLMAgent:
    player: Player
    personality: Personality
    all_players: list[Player]
    client: object  # LLMClient or compatible (FakeLLMClient in tests)
    fallback: PlayerAgent

    # --- prompt construction -------------------------------------------------

    def _system_prompt(self) -> str:
        opinion_lines = "\n".join(
            f"  Player {pid}: {score:+.2f}"
            for pid, score in sorted(self.personality.opinions.items())
        )
        roster = ", ".join(f"Player {p.id}" for p in self.all_players)
        return (
            f"You are Player {self.player.id} in a 5-player game of Secret Hitler.\n"
            f"Your role: {self.player.role.value.upper()}.\n"
            f"Your alignment desire (+1 wants Liberal outcomes .. -1 wants Fascist outcomes): "
            f"{self.personality.desire:+.2f}.\n"
            f"Your initial opinions of other players (-1 distrust .. +1 trust):\n"
            f"{opinion_lines}\n"
            f"Public roster: {roster}.\n\n"
            "Rules summary:\n"
            "- Liberals win by enacting 5 Liberal policies or executing Hitler.\n"
            "- Fascists win by enacting 6 Fascist policies, or by electing Hitler "
            "as Chancellor after 3 Fascist policies are enacted.\n"
            "- Be strategic and stay in character. Never reveal your role unless "
            "doing so helps you win."
        )

    def _nominate_user_prompt(self, eligible: list[Player]) -> str:
        ids = [p.id for p in eligible]
        return (
            "You are the President this round. Pick a Chancellor from the "
            "eligible candidates.\n"
            f"Eligible: {ids}\n"
            'Reply with ONLY the player number (e.g. "3"). No explanation.'
        )

    def _vote_user_prompt(self, president: Player, nominee: Player) -> str:
        return (
            f"The President is Player {president.id}. They nominated Player "
            f"{nominee.id} as Chancellor.\n"
            "Vote ja or nein on this government.\n"
            'Reply with ONLY one word: "ja" or "nein". No explanation.'
        )

    # --- decisions -----------------------------------------------------------

    def nominate(self, eligible: list[Player]) -> Player:
        if getattr(self.client, "is_exhausted", False):
            return self.fallback.nominate(eligible)

        eligible_ids = {p.id for p in eligible}
        system = self._system_prompt()
        user = self._nominate_user_prompt(eligible)

        for attempt in range(2):
            try:
                reply = self.client.chat(system, user)
            except RuntimeError:
                return self.fallback.nominate(eligible)

            chosen_id = self._parse_player_id(reply, eligible_ids)
            if chosen_id is not None:
                return next(p for p in eligible if p.id == chosen_id)
            user = (
                "Your previous reply was invalid. "
                + self._nominate_user_prompt(eligible)
            )

        print(
            f"[agent] Player {self.player.id} LLM gave invalid nominations twice; "
            "falling back to random",
            file=sys.stderr,
        )
        return self.fallback.nominate(eligible)

    def vote(self, president: Player, nominee: Player) -> bool:
        if getattr(self.client, "is_exhausted", False):
            return self.fallback.vote(president, nominee)

        system = self._system_prompt()
        user = self._vote_user_prompt(president, nominee)

        for attempt in range(2):
            try:
                reply = self.client.chat(system, user)
            except RuntimeError:
                return self.fallback.vote(president, nominee)

            parsed = self._parse_vote(reply)
            if parsed is not None:
                return parsed
            user = (
                "Your previous reply was invalid. "
                + self._vote_user_prompt(president, nominee)
            )

        print(
            f"[agent] Player {self.player.id} LLM gave invalid votes twice; "
            "falling back to random",
            file=sys.stderr,
        )
        return self.fallback.vote(president, nominee)

    # --- parsing -------------------------------------------------------------

    @staticmethod
    def _parse_player_id(reply: str, allowed: set[int]) -> Optional[int]:
        match = _INTEGER_RE.search(reply or "")
        if match is None:
            return None
        candidate = int(match.group())
        return candidate if candidate in allowed else None

    @staticmethod
    def _parse_vote(reply: str) -> Optional[bool]:
        token = (reply or "").strip().lower()
        # Strip surrounding punctuation/quotes for tolerance.
        token = token.strip(".,!\"'`* ")
        return _VALID_VOTES.get(token)


# --- adapters: agents -> engine callbacks ------------------------------------


def make_choose_fn(agents: dict[int, PlayerAgent]) -> ChooseFn:
    def choose_fn(president: Player, eligible: list[Player]) -> Player:
        return agents[president.id].nominate(eligible)

    return choose_fn


def make_vote_fn(agents: dict[int, PlayerAgent]) -> VoteFn:
    def vote_fn(voter: Player, president: Player, nominee: Player) -> bool:
        return agents[voter.id].vote(president, nominee)

    return vote_fn
