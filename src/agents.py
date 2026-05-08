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

from src.game import (
    ChooseFn,
    DiscardFn,
    EnactFn,
    ExecuteFn,
    Player,
    Role,
    RoundEvent,
    Statement,
    VoteFn,
)
from src.personality import Personality
from src.policies import Policy
from src.prompts import (
    discard_prompt,
    enact_prompt,
    execute_prompt,
    lie_check_prompt,
    nominate_prompt,
    retry_prompt,
    statement_prompt,
    system_prompt,
    update_predicted_roles_prompt,
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
    last_statement_reasoning: str
    last_update_reasoning: str
    last_execute_reasoning: str
    private_log: list[str]

    def nominate(self, eligible: list[Player]) -> Player: ...
    def vote(self, president: Player, nominee: Player) -> bool: ...
    def discard_policy(self, hand: list[Policy]) -> Policy: ...
    def enact_policy(self, hand: list[Policy]) -> Policy: ...
    def execute_player(self, targets: list[Player]) -> Player: ...
    def make_statement(
        self,
        enacted: Policy,
        drawn_hand: Optional[list[Policy]],
        chancellor_hand: Optional[list[Policy]],
        president_id: int,
        chancellor_id: int,
        liberal_tally: int,
        fascist_tally: int,
        prior_statements: Optional[list[Statement]] = None,
    ) -> Statement: ...
    def update_predicted_roles(
        self, statements_this_round: list[Statement]
    ) -> dict[int, float]: ...


@dataclass
class RandomAgent:
    player: Player
    seed: Optional[int] = None
    last_nominate_reasoning: str = ""
    last_vote_reasoning: str = ""
    last_discard_reasoning: str = ""
    last_enact_reasoning: str = ""
    last_statement_reasoning: str = ""
    last_update_reasoning: str = ""
    last_execute_reasoning: str = ""
    private_log: list[str] = field(default_factory=list)

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

    def execute_player(self, targets: list[Player]) -> Player:
        chosen = self._rng.choice(targets)
        self.last_execute_reasoning = _RANDOM_REASONING
        return chosen

    def make_statement(
        self,
        enacted: Policy,
        drawn_hand: Optional[list[Policy]],
        chancellor_hand: Optional[list[Policy]],
        president_id: int = 0,
        chancellor_id: int = 0,
        liberal_tally: int = 0,
        fascist_tally: int = 0,
        prior_statements: Optional[list[Statement]] = None,
    ) -> Statement:
        self.last_statement_reasoning = _RANDOM_REASONING
        return Statement(
            player_id=self.player.id, text="(silent)", reasoning=_RANDOM_REASONING
        )

    def update_predicted_roles(
        self, statements_this_round: list[Statement]
    ) -> dict[int, float]:
        # Random agent doesn't update — runner uses heuristic for random mode.
        self.last_update_reasoning = _RANDOM_REASONING
        return {}


@dataclass
class LLMAgent:
    player: Player
    personality: Personality
    all_players: list[Player]
    client: object  # LLMClient or compatible (FakeLLMClient in tests)
    fallback: PlayerAgent
    history: list[RoundEvent] = field(default_factory=list)
    private_log: list[str] = field(default_factory=list)
    last_nominate_reasoning: str = ""
    last_vote_reasoning: str = ""
    last_discard_reasoning: str = ""
    last_enact_reasoning: str = ""
    last_statement_reasoning: str = ""
    last_update_reasoning: str = ""
    last_execute_reasoning: str = ""

    # Prompts now live in src/prompts.py — easier to find and tweak.

    # --- decisions -----------------------------------------------------------

    def discard_policy(self, hand: list[Policy]) -> Policy:
        if getattr(self.client, "is_exhausted", False):
            return self._discard_fallback(hand)

        system = system_prompt(
            self.player,
            self.personality,
            self.all_players,
            history=self.history,
            private_log=self.private_log,
        )
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

    def execute_player(self, targets: list[Player]) -> Player:
        if getattr(self.client, "is_exhausted", False):
            return self._execute_fallback(targets)

        target_ids = {p.id for p in targets}
        # The execution prompt needs the current Fascist tally; pull it from
        # the latest history snapshot so we don't have to plumb state through.
        f_tally = self.history[-1].fascist_tally if self.history else 0

        system = system_prompt(
            self.player,
            self.personality,
            self.all_players,
            history=self.history,
            private_log=self.private_log,
        )
        base_user = execute_prompt(targets, fascist_tally=f_tally)
        user = base_user

        for _ in range(2):
            try:
                reply = self.client.chat(system, user, json_mode=True)
            except RuntimeError:
                return self._execute_fallback(targets)

            parsed = self._parse_execute_reply(reply, target_ids)
            if parsed is not None:
                target_id, reasoning = parsed
                self.last_execute_reasoning = reasoning
                return next(p for p in targets if p.id == target_id)
            user = retry_prompt(base_user, "ineligible execute_id or invalid JSON")

        print(
            f"[agent] Player {self.player.id} LLM gave invalid execution targets twice; "
            "falling back to random",
            file=sys.stderr,
        )
        return self._execute_fallback(targets)

    def enact_policy(self, hand: list[Policy]) -> Policy:
        if getattr(self.client, "is_exhausted", False):
            return self._enact_fallback(hand)

        system = system_prompt(
            self.player,
            self.personality,
            self.all_players,
            history=self.history,
            private_log=self.private_log,
        )
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
        system = system_prompt(
            self.player,
            self.personality,
            self.all_players,
            history=self.history,
            private_log=self.private_log,
        )
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

        system = system_prompt(
            self.player,
            self.personality,
            self.all_players,
            history=self.history,
            private_log=self.private_log,
        )
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

    # --- discussion phase ----------------------------------------------------

    def make_statement(
        self,
        enacted: Policy,
        drawn_hand: Optional[list[Policy]],
        chancellor_hand: Optional[list[Policy]],
        president_id: int = 0,
        chancellor_id: int = 0,
        liberal_tally: int = 0,
        fascist_tally: int = 0,
        prior_statements: Optional[list[Statement]] = None,
    ) -> Statement:
        if getattr(self.client, "is_exhausted", False):
            self.last_statement_reasoning = _FALLBACK_REASONING
            return Statement(
                player_id=self.player.id, text="(silent)", reasoning=_FALLBACK_REASONING
            )

        system = system_prompt(
            self.player,
            self.personality,
            self.all_players,
            history=self.history,
            private_log=self.private_log,
        )
        base_user = statement_prompt(
            enacted=enacted,
            drawn_hand=drawn_hand,
            chancellor_hand=chancellor_hand,
            liberal_tally=liberal_tally,
            fascist_tally=fascist_tally,
            president_id=president_id,
            chancellor_id=chancellor_id,
            prior_statements=prior_statements,
        )
        user = base_user

        for _ in range(2):
            try:
                reply = self.client.chat(system, user, json_mode=True)
            except RuntimeError:
                self.last_statement_reasoning = _FALLBACK_REASONING
                return Statement(
                    player_id=self.player.id,
                    text="(silent)",
                    reasoning=_FALLBACK_REASONING,
                )
            parsed = self._parse_statement_reply(reply)
            if parsed is not None:
                text, reasoning = parsed
                # For Fascist/Hitler players, run a self-check pass that
                # reviews the statement and rewrites it if it admits the
                # role. The check uses the same client + system prompt.
                if self.player.role in (Role.FASCIST, Role.HITLER):
                    text = self._self_check_lie(
                        text,
                        system=system,
                        drawn_hand=drawn_hand,
                        chancellor_hand=chancellor_hand,
                        enacted=enacted,
                    )
                self.last_statement_reasoning = reasoning
                return Statement(
                    player_id=self.player.id, text=text, reasoning=reasoning
                )
            user = retry_prompt(base_user, "missing or invalid 'statement' field")

        print(
            f"[agent] Player {self.player.id} LLM gave invalid statements twice; "
            "falling silent",
            file=sys.stderr,
        )
        self.last_statement_reasoning = _FALLBACK_REASONING
        return Statement(
            player_id=self.player.id, text="(silent)", reasoning=_FALLBACK_REASONING
        )

    def update_predicted_roles(
        self, statements_this_round: list[Statement]
    ) -> dict[int, float]:
        if getattr(self.client, "is_exhausted", False):
            self.last_update_reasoning = _FALLBACK_REASONING
            return dict(self.personality.predicted_roles)

        system = system_prompt(
            self.player,
            self.personality,
            self.all_players,
            history=self.history,
            private_log=self.private_log,
        )
        base_user = update_predicted_roles_prompt(
            current_predicted_roles=self.personality.predicted_roles,
            statements=statements_this_round,
        )
        user = base_user

        allowed_ids = {
            p.id for p in self.all_players if p.id != self.player.id
        }

        for _ in range(2):
            try:
                reply = self.client.chat(system, user, json_mode=True)
            except RuntimeError:
                self.last_update_reasoning = _FALLBACK_REASONING
                return dict(self.personality.predicted_roles)
            parsed = self._parse_update_reply(reply, allowed_ids)
            if parsed is not None:
                deltas, reasoning = parsed
                self.last_update_reasoning = reasoning
                # Apply: keep existing values, override the keys in deltas.
                for pid, val in deltas.items():
                    self.personality.predicted_roles[pid] = max(-1.0, min(1.0, val))
                return dict(self.personality.predicted_roles)
            user = retry_prompt(base_user, "missing/invalid 'predicted_roles' field")

        print(
            f"[agent] Player {self.player.id} LLM gave invalid role-updates twice; "
            "preserving previous values",
            file=sys.stderr,
        )
        self.last_update_reasoning = _FALLBACK_REASONING
        return dict(self.personality.predicted_roles)

    def _self_check_lie(
        self,
        statement_text: str,
        system: str,
        drawn_hand: Optional[list[Policy]],
        chancellor_hand: Optional[list[Policy]],
        enacted: Policy,
    ) -> str:
        """Fascist/Hitler-only second-pass: have the LLM inspect its own
        statement and rewrite it if it admits the role. Best-effort — if the
        check call fails or returns garbage, fall back to the original."""
        if getattr(self.client, "is_exhausted", False):
            return statement_text
        check_user = lie_check_prompt(
            role=self.player.role,
            statement_text=statement_text,
            drawn_hand=drawn_hand,
            chancellor_hand=chancellor_hand,
            enacted=enacted,
        )
        try:
            reply = self.client.chat(system, check_user, json_mode=True)
        except RuntimeError:
            return statement_text
        try:
            data = json.loads(reply or "")
        except (json.JSONDecodeError, TypeError):
            return statement_text
        if not isinstance(data, dict):
            return statement_text
        admits = data.get("admits_outing")
        rewritten = data.get("rewritten")
        if admits is True and isinstance(rewritten, str) and rewritten.strip():
            return rewritten.strip()
        return statement_text

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

    def _execute_fallback(self, targets: list[Player]) -> Player:
        result = self.fallback.execute_player(targets)
        self.last_execute_reasoning = _FALLBACK_REASONING
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
    def _parse_statement_reply(reply: str) -> Optional[tuple[str, str]]:
        try:
            data = json.loads(reply or "")
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        text = data.get("statement")
        if not isinstance(text, str) or not text.strip():
            return None
        reasoning = data.get("reasoning", "")
        if not isinstance(reasoning, str):
            reasoning = ""
        return text.strip(), reasoning

    @staticmethod
    def _parse_update_reply(
        reply: str, allowed_ids: set[int]
    ) -> Optional[tuple[dict[int, float], str]]:
        try:
            data = json.loads(reply or "")
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        raw = data.get("predicted_roles")
        if not isinstance(raw, dict):
            return None
        deltas: dict[int, float] = {}
        for k, v in raw.items():
            try:
                pid = int(k)
            except (TypeError, ValueError):
                continue
            if pid not in allowed_ids:
                continue
            if isinstance(v, (int, float)):
                deltas[pid] = float(v)
        reasoning = data.get("reasoning", "")
        if not isinstance(reasoning, str):
            reasoning = ""
        return deltas, reasoning

    @staticmethod
    def _parse_execute_reply(
        reply: str, allowed_ids: set[int]
    ) -> Optional[tuple[int, str]]:
        try:
            data = json.loads(reply or "")
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        target_id = data.get("execute_id")
        if not isinstance(target_id, int) or target_id not in allowed_ids:
            return None
        reasoning = data.get("reasoning", "")
        if not isinstance(reasoning, str):
            reasoning = ""
        return target_id, reasoning

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


def make_execute_fn(agents: dict[int, PlayerAgent]) -> ExecuteFn:
    def execute_fn(president: Player, targets: list[Player]) -> Player:
        return agents[president.id].execute_player(targets)

    return execute_fn


# --- ScriptedAgent: force mechanical decisions, delegate reactive ones ------


_SCRIPTED_REASONING = "(scripted)"


@dataclass
class ScriptedAgent:
    """Wraps another PlayerAgent. Mechanical decisions can be pre-scripted via
    the `scripted` dict; everything else (statements, predicted_role updates)
    delegates to the wrapped agent. See specs/scripted_agent.md and
    specs/round_bounded_scripting.md.
    """

    player: Player
    fallback: PlayerAgent
    scripted: dict = field(default_factory=dict)
    apply_until_round: Optional[int] = None
    history_ref: list = field(default_factory=list)
    private_log: list[str] = field(default_factory=list)
    last_nominate_reasoning: str = ""
    last_vote_reasoning: str = ""
    last_discard_reasoning: str = ""
    last_enact_reasoning: str = ""
    last_statement_reasoning: str = ""
    last_update_reasoning: str = ""
    last_execute_reasoning: str = ""

    def __post_init__(self) -> None:
        # Share the same private_log object as the fallback so the runner's
        # appends (which target agents[pid].private_log) are visible to the
        # underlying LLMAgent's prompts.
        self.private_log = self.fallback.private_log

    def _scripts_active(self) -> bool:
        if self.apply_until_round is None:
            return True
        current_round = len(self.history_ref) + 1
        return current_round <= self.apply_until_round

    def nominate(self, eligible: list[Player]) -> Player:
        if "nominate" in self.scripted and self._scripts_active():
            target_id = self.scripted["nominate"]
            try:
                target = next(p for p in eligible if p.id == target_id)
            except StopIteration:
                raise ValueError(
                    f"Scripted nominate={target_id} but eligible candidates are "
                    f"{[p.id for p in eligible]}"
                )
            self.last_nominate_reasoning = _SCRIPTED_REASONING
            return target
        result = self.fallback.nominate(eligible)
        self.last_nominate_reasoning = self.fallback.last_nominate_reasoning
        return result

    def vote(self, president: Player, nominee: Player) -> bool:
        if "vote" in self.scripted and self._scripts_active():
            self.last_vote_reasoning = _SCRIPTED_REASONING
            return bool(self.scripted["vote"])
        result = self.fallback.vote(president, nominee)
        self.last_vote_reasoning = self.fallback.last_vote_reasoning
        return result

    def discard_policy(self, hand: list[Policy]) -> Policy:
        if "discard" in self.scripted and self._scripts_active():
            target = self.scripted["discard"]
            if target not in hand:
                raise ValueError(
                    f"Scripted discard={target.value} but hand is "
                    f"{[p.value for p in hand]}"
                )
            self.last_discard_reasoning = _SCRIPTED_REASONING
            return target
        result = self.fallback.discard_policy(hand)
        self.last_discard_reasoning = self.fallback.last_discard_reasoning
        return result

    def enact_policy(self, hand: list[Policy]) -> Policy:
        if "enact" in self.scripted and self._scripts_active():
            target = self.scripted["enact"]
            if target not in hand:
                raise ValueError(
                    f"Scripted enact={target.value} but hand is "
                    f"{[p.value for p in hand]}"
                )
            self.last_enact_reasoning = _SCRIPTED_REASONING
            return target
        result = self.fallback.enact_policy(hand)
        self.last_enact_reasoning = self.fallback.last_enact_reasoning
        return result

    def execute_player(self, targets: list[Player]) -> Player:
        if "execute" in self.scripted and self._scripts_active():
            target_id = self.scripted["execute"]
            try:
                target = next(p for p in targets if p.id == target_id)
            except StopIteration:
                raise ValueError(
                    f"Scripted execute={target_id} but eligible targets are "
                    f"{[p.id for p in targets]}"
                )
            self.last_execute_reasoning = _SCRIPTED_REASONING
            return target
        result = self.fallback.execute_player(targets)
        self.last_execute_reasoning = self.fallback.last_execute_reasoning
        return result

    # --- reactive calls always delegate ---

    def make_statement(
        self,
        enacted: Policy,
        drawn_hand: Optional[list[Policy]],
        chancellor_hand: Optional[list[Policy]],
        president_id: int = 0,
        chancellor_id: int = 0,
        liberal_tally: int = 0,
        fascist_tally: int = 0,
        prior_statements: Optional[list[Statement]] = None,
    ) -> Statement:
        result = self.fallback.make_statement(
            enacted=enacted,
            drawn_hand=drawn_hand,
            chancellor_hand=chancellor_hand,
            president_id=president_id,
            chancellor_id=chancellor_id,
            liberal_tally=liberal_tally,
            fascist_tally=fascist_tally,
            prior_statements=prior_statements,
        )
        self.last_statement_reasoning = self.fallback.last_statement_reasoning
        return result

    def update_predicted_roles(
        self, statements_this_round: list[Statement]
    ) -> dict[int, float]:
        result = self.fallback.update_predicted_roles(statements_this_round)
        self.last_update_reasoning = self.fallback.last_update_reasoning
        return result


def build_scripted_agents(
    base_agents: dict[int, PlayerAgent],
    scripts: dict[int, dict],
    *,
    apply_until_round: Optional[int] = None,
) -> dict[int, PlayerAgent]:
    """Wrap selected base_agents with ScriptedAgent. Untouched ids keep their
    original agent (LLM, random, etc.). Returns a new dict; does not mutate
    base_agents.

    If `apply_until_round` is set, scripts only apply for rounds <= that
    number; later rounds delegate to the fallback (free LLM play).
    """
    out: dict[int, PlayerAgent] = dict(base_agents)
    for pid, script in scripts.items():
        if pid not in out:
            raise KeyError(f"Player {pid} not in base_agents")
        fallback = out[pid]
        out[pid] = ScriptedAgent(
            player=fallback.player,
            fallback=fallback,
            scripted=dict(script),
            apply_until_round=apply_until_round,
            history_ref=getattr(fallback, "history", []),
        )
    return out
