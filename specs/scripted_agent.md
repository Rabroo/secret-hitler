# Spec: ScriptedAgent (Force Decisions, LLM Reacts)

## Goal
Let scenario authors **force the mechanical decisions** of one or more
players (nominate, vote, discard, enact, execute) and let the LLM still do
all the *reactive* work (make_statement, update_predicted_roles). Use case
from the operator's notes: "let them happen and then let them react more
than choose."

The existing `RandomAgent` and `LLMAgent` both *decide* mechanically. There's
no way today to script a specific decision. `ScriptedAgent` fills that gap.

## Design
A `ScriptedAgent` wraps any other `PlayerAgent` (typically `LLMAgent`):

- **Mechanical decisions** (nominate, vote, discard, enact, execute): if a
  scripted value is present for that decision type, return it immediately.
  Otherwise delegate to the wrapped agent.
- **Reactive decisions** (make_statement, update_predicted_roles): always
  delegate to the wrapped agent — these are what the operator is studying.

## Class shape
```python
@dataclass
class ScriptedAgent:
    player: Player
    fallback: PlayerAgent              # the LLM (or random) it wraps
    scripted: dict[str, Any] = ...     # keyed by decision-type name

    # Reasoning fields are mirrored from fallback after each scripted call so
    # the dashboard renders something useful for the operator. For statement
    # and update calls they're whatever the fallback writes.
```

`scripted` keys (all optional):
- `"nominate"`: int — target player id (must be in eligible)
- `"vote"`: bool — ja=True, nein=False
- `"discard"`: Policy — must be in hand
- `"enact"`: Policy — must be in hand
- `"execute"`: int — target player id (must be alive non-self)

Missing key → call falls through to `self.fallback`.

## Behaviour rules
- `last_*_reasoning` for scripted decisions is set to `"(scripted)"` so the
  dashboard makes the source clear.
- Validation is *defensive*: if the scripted value isn't actually legal
  (e.g. discard a policy not in hand), raise `ValueError`. We don't want
  scenarios to silently produce nonsense.
- For `discard` / `enact`: scripted value matches by Policy enum value, not
  by index. If the hand has duplicates, `list.remove(target)` semantics —
  identical to engine's `_remove_policy`.
- `make_statement` and `update_predicted_roles` always delegate, never
  scripted. (If you want to script a statement string too, that's a
  follow-up; the rulebook scenarios mostly care about belief updates,
  which need the LLM.)

## Construction sugar
A small helper in the runner / scenarios so authors don't have to wire each
agent individually:

```python
def build_scripted_agents(
    base_agents: dict[int, PlayerAgent],
    scripts: dict[int, dict[str, Any]],
) -> dict[int, PlayerAgent]:
    """Wrap base_agents with ScriptedAgent for any player id present in scripts."""
```

Untouched player ids keep their original agent (LLM or random).

## Example use
```python
# Force Pres P1 to nominate P3, P3 (Fascist Chan) to enact F:
agents = build_agents("llm", players, ...)
agents = build_scripted_agents(
    agents,
    {
        1: {"nominate": 3, "discard": Policy.LIBERAL},   # Pres passes F+F-ish
        3: {"enact": Policy.FASCIST},                     # Chan picks F
    },
)
```

Everyone still votes freely (since `"vote"` isn't scripted). All five players
still make statements + update predicted_roles via their LLM.

## Tests
- ScriptedAgent.nominate returns the scripted player when key present.
- ScriptedAgent.nominate falls back when key absent.
- ScriptedAgent.vote / discard / enact / execute likewise.
- ScriptedAgent raises on illegal scripted value (e.g. discard policy
  not in hand).
- ScriptedAgent.make_statement always delegates (returns fallback's
  Statement).
- ScriptedAgent.update_predicted_roles always delegates.
- `last_*_reasoning` is set to `"(scripted)"` for scripted decisions and
  to the fallback's reasoning for delegated decisions.

## Out of scope
- Round-keyed scripts (different decisions in different rounds). For multi-
  round scripted scenarios, the author can mutate `scripted_agent.scripted`
  between rounds; we don't bake round numbers into the agent.
- Scripting `make_statement` (would defeat the purpose — we want the LLM to
  react).

## Dependencies
Stdlib only.
