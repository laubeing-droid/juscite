"""F28 single-agent loop budget face (W3-U04): round/token/cost/time caps
plus the no-progress breaker, converging the tool face on over-limit.

Contract (06:F28 assertion + 17 card + 05:37 机械暂停紧箍咒):
- 用户可不设轮数上限 — round_cap=None is a first-class configuration; with no
  round cap the loop is never paused for round count alone (the closed
  boundary vocabulary has no "rounds" boundary; a configured round cap fires
  as the BUDGET_LIMIT rounds form).
- 次数无限≠费用无限 — unlimited rounds still converge on the token / cost /
  time / no-progress / permission boundaries.
- 不无限撞同一失败 — max_identical_failures consecutive turns with the SAME
  failure signature trip NO_PROGRESS instead of colliding forever.
- 授权/法律缺口 — a permission-family failure code trips PERMISSION_MISSING
  immediately (retrying an authorization gap is not progress).
- 超限收敛工具面 — an exceeded verdict is written to the REAL harness goal
  ledger by the coordinator (pause_goal, boundary + triggerValue + time), so
  the next preflight blocks: the tool face converges (zero further prompts)
  and stays paused until the explicit user resume (目标可续, resume is the
  only wake-up channel, E07 §5.3).

Deterministic and money-safe: cost is integer minor (分) end-to-end — float
cost inputs are refused typed (Decimal/整分 red line). The meter itself holds
no clock dependency: elapsed time is supplied per turn record by the caller
(coordinator measures with time.monotonic), so evaluation is reproducible.

Durable truth note: the meter is per-episode in-memory by design — the
durable convergence fact is the harness goal pause row (survives restarts;
preflight reads it); after an explicit resume a fresh meter episode starts.
"""
from __future__ import annotations

import json

from goal_basis import PAUSE_REASONS

SCHEMA = "juscite-f28-turn-budget/1"

# Boundary set is the SAME closed vocabulary as goal_basis.PAUSE_REASONS /
# harness GOAL_PAUSE_BOUNDARIES — F28 adds no new boundary name.
BOUNDARIES = PAUSE_REASONS

# Fixed deterministic precedence when several caps are exceeded at once.
_PRECEDENCE = ("PERMISSION_MISSING", "NO_PROGRESS", "BUDGET_LIMIT", "TIME_LIMIT")

_POLICY_FIELDS = ("round_cap", "token_cap", "cost_cap_minor", "time_cap_s",
                  "max_identical_failures")


class BudgetError(ValueError):
    """Typed refusal; str(exc) is a bare f28_* code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _int_cap(value, field: str, *, allow_none: bool = True):
    if value is None and allow_none:
        return None
    # bool is an int subclass — refuse it explicitly; float money is refused.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BudgetError("f28_policy_invalid_value:" + field)
    return value


class BudgetPolicy:
    """Immutable budget policy. round_cap=None = 用户不设轮数上限（合法）。"""

    __slots__ = _POLICY_FIELDS

    def __init__(self, *, round_cap=None, token_cap=None, cost_cap_minor=None,
                 time_cap_s=None, max_identical_failures=3):
        self.round_cap = _int_cap(round_cap, "round_cap")
        self.token_cap = _int_cap(token_cap, "token_cap")
        self.cost_cap_minor = _int_cap(cost_cap_minor, "cost_cap_minor")
        if time_cap_s is not None:
            if isinstance(time_cap_s, bool) or not isinstance(time_cap_s, (int, float)) \
                    or time_cap_s < 0:
                raise BudgetError("f28_policy_invalid_value:time_cap_s")
        self.time_cap_s = time_cap_s
        self.max_identical_failures = _int_cap(
            max_identical_failures, "max_identical_failures", allow_none=False)
        if self.max_identical_failures < 1:
            raise BudgetError("f28_policy_invalid_value:max_identical_failures")

    @classmethod
    def from_mapping(cls, mapping) -> "BudgetPolicy":
        if not isinstance(mapping, dict):
            raise BudgetError("f28_policy_invalid")
        unknown = sorted(set(mapping) - set(_POLICY_FIELDS))
        if unknown:
            raise BudgetError("f28_policy_unknown_field:" + ",".join(unknown))
        return cls(**mapping)

    def as_dict(self) -> dict:
        return {field: getattr(self, field) for field in _POLICY_FIELDS}


class BudgetGate:
    """Per-episode meter + deterministic over-limit verdicts."""

    def __init__(self, policy: BudgetPolicy):
        if not isinstance(policy, BudgetPolicy):
            raise BudgetError("f28_policy_invalid")
        self.policy = policy
        self.rounds = 0
        self.tokens = 0
        self.cost_minor = 0
        self.elapsed_s = 0.0
        self.failures = 0            # consecutive identical-failure streak
        self.last_failure_code = None
        self.verdicts: list[dict] = []

    # -- recording ----------------------------------------------------------

    def reset(self) -> None:
        """Fresh episode after an explicit user resume (E07 §5.3): consumed
        counters and streaks zero, policy unchanged. The durable pause fact
        already lives in the goal ledger; the meter only measures episodes."""
        self.rounds = 0
        self.tokens = 0
        self.cost_minor = 0
        self.elapsed_s = 0.0
        self.failures = 0
        self.last_failure_code = None
        self.verdicts = []

    def record_turn(self, *, tokens: int = 0, cost_minor: int = 0,
                    elapsed_s: float = 0.0,
                    failure_code: str | None = None) -> dict:
        """Record one loop turn (advance attempt) and evaluate the caps."""
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
            raise BudgetError("f28_tokens_invalid")
        if isinstance(cost_minor, bool) or not isinstance(cost_minor, int):
            # 金额一律整分：float 成本具名拒收（Decimal/整分红线）。
            raise BudgetError("f28_cost_not_minor_units")
        if isinstance(elapsed_s, bool) or not isinstance(elapsed_s, (int, float)) \
                or elapsed_s < 0:
            raise BudgetError("f28_elapsed_invalid")
        if failure_code is not None and (
                not isinstance(failure_code, str) or not failure_code):
            raise BudgetError("f28_failure_code_invalid")
        self.rounds += 1
        self.tokens += tokens
        self.cost_minor += cost_minor
        self.elapsed_s += float(elapsed_s)
        if failure_code is None:
            self.failures = 0
            self.last_failure_code = None
        else:
            if failure_code == self.last_failure_code:
                self.failures += 1
            else:
                self.failures = 1
                self.last_failure_code = failure_code
        verdict = self._evaluate(failure_code)
        if verdict["exceeded"]:
            self.verdicts.append(verdict)
        return verdict

    # -- evaluation ---------------------------------------------------------

    def _candidates(self, failure_code: str | None) -> dict:
        """Boundary candidates with deterministic trigger values."""
        candidates = {}
        if failure_code is not None and failure_code.startswith("permission"):
            candidates["PERMISSION_MISSING"] = {
                "triggerValue": failure_code,
                "detail": {"kind": "authorization_gap", "code": failure_code},
            }
        if (failure_code is not None
                and self.failures >= self.policy.max_identical_failures):
            candidates["NO_PROGRESS"] = {
                "triggerValue": "identical_failure:{}:{}".format(
                    self.failures, failure_code),
                "detail": {"kind": "no_progress_breaker",
                           "streak": self.failures,
                           "max": self.policy.max_identical_failures,
                           "code": failure_code},
            }
        budget = None
        if self.policy.token_cap is not None and self.tokens > self.policy.token_cap:
            budget = {"triggerValue": "tokens:{}>{}".format(
                self.tokens, self.policy.token_cap),
                "detail": {"kind": "token_budget", "tokens": self.tokens,
                           "cap": self.policy.token_cap}}
        if (self.policy.cost_cap_minor is not None
                and self.cost_minor > self.policy.cost_cap_minor):
            budget = budget or {"triggerValue": "cost_minor:{}>{}".format(
                self.cost_minor, self.policy.cost_cap_minor),
                "detail": {"kind": "cost_budget",
                           "cost_minor": self.cost_minor,
                           "cap": self.policy.cost_cap_minor}}
        if self.policy.round_cap is not None and self.rounds > self.policy.round_cap:
            budget = budget or {"triggerValue": "rounds:{}>{}".format(
                self.rounds, self.policy.round_cap),
                "detail": {"kind": "round_budget", "rounds": self.rounds,
                           "cap": self.policy.round_cap}}
        if budget is not None:
            candidates["BUDGET_LIMIT"] = budget
        if self.policy.time_cap_s is not None \
                and self.elapsed_s > self.policy.time_cap_s:
            candidates["TIME_LIMIT"] = {
                "triggerValue": "elapsed_s:{}>{}".format(
                    round(self.elapsed_s, 3), self.policy.time_cap_s),
                "detail": {"kind": "time_budget",
                           "elapsed_s": round(self.elapsed_s, 3),
                           "cap": self.policy.time_cap_s}}
        return candidates

    def _evaluate(self, failure_code: str | None) -> dict:
        candidates = self._candidates(failure_code)
        for boundary in _PRECEDENCE:
            if boundary in candidates:
                hit = candidates[boundary]
                verdict = {
                    "schema": SCHEMA,
                    "exceeded": True,
                    "boundary": boundary,
                    "triggerValue": hit["triggerValue"],
                    "detail": hit["detail"],
                    "rounds": self.rounds,
                }
                return verdict
        return {"schema": SCHEMA, "exceeded": False, "boundary": None,
                "triggerValue": None, "detail": {}, "rounds": self.rounds}

    # -- 工具面：over-limit status projection (UI/CLI consumption) ----------

    def projection(self, *, open_pause: dict | None = None) -> dict:
        def cap_state(value, cap):
            if cap is None:
                return "unset"
            return "exceeded" if value > cap else "ok"

        streak = self.failures if self.last_failure_code else 0
        return {
            "schema": SCHEMA,
            "face": "budget.projection",
            "policy": {**self.policy.as_dict(),
                       "roundCapSet": self.policy.round_cap is not None},
            "consumed": {"rounds": self.rounds, "tokens": self.tokens,
                         "cost_minor": self.cost_minor,
                         "elapsed_s": round(self.elapsed_s, 3),
                         "identical_failure_streak": streak},
            "caps": {
                "rounds": cap_state(self.rounds, self.policy.round_cap),
                "tokens": cap_state(self.tokens, self.policy.token_cap),
                "cost_minor": cap_state(self.cost_minor, self.policy.cost_cap_minor),
                "time": cap_state(self.elapsed_s, self.policy.time_cap_s),
            },
            "exceededVerdicts": list(self.verdicts),
            "openPause": open_pause,
            "resumable": open_pause is not None,
            "resume": {"method": "harness.resume_goal", "explicit": True},
        }


def face_call(method: str, args: dict) -> dict:
    """Closed stateless dispatch (legal_entry budget.* group).

    The meter is per-episode; the stateless CLI face evaluates a caller-
    supplied turn record list (the durable boundary truth itself always
    lives in the harness goal ledger, not here).
    """
    if not isinstance(args, dict):
        raise BudgetError("f28_params_invalid")
    policy = BudgetPolicy.from_mapping(args.get("policy") or {})
    turns = args.get("turns")
    if not isinstance(turns, list):
        raise BudgetError("f28_turns_required")
    gate = BudgetGate(policy)
    verdicts = []
    for turn in turns:
        if not isinstance(turn, dict):
            raise BudgetError("f28_turn_invalid")
        verdict = gate.record_turn(
            tokens=turn.get("tokens", 0),
            cost_minor=turn.get("cost_minor", 0),
            elapsed_s=turn.get("elapsed_s", 0.0),
            failure_code=turn.get("failure_code"))
        verdicts.append(verdict)
        if verdict["exceeded"]:
            break  # converged: the loop stops issuing further turns
    final = verdicts[-1] if verdicts else {
        "schema": SCHEMA, "exceeded": False, "boundary": None,
        "triggerValue": None, "detail": {}, "rounds": 0}
    result = {"schema": SCHEMA, "face": method, "verdict": final,
              "evaluatedRounds": len(verdicts),
              "projection": gate.projection()}
    if method == "budget.evaluate":
        result["detail_json"] = json.dumps(final.get("detail") or {},
                                           ensure_ascii=False, sort_keys=True)
    return result
