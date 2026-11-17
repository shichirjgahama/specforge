"""Eight executable properties checked against the specification and runtime.

These are not unit tests of one function: each property is a small model check
or exhaustive scan over an input domain, with seeded random walks for stateful
properties. The same checks are reused by the hypothesis tests after a change
request is applied.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterable

from .ast_nodes import Program
from .interpreter import EvalError, Interpreter
from ..runtime.engine import Simulation


@dataclass
class PropertyResult:
    name: str
    ok: bool
    violations: list[str] = field(default_factory=list)
    checks: int = 0

    def to_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "checks": self.checks,
                "violations": self.violations}


def _allowed(program: Program) -> set[tuple[str, str, str, str]]:
    result = set()
    for state in program.states:
        for edge in state.edges:
            result.add((state.name, edge.source, edge.target, edge.event))
    return result


def _world_for_invariants(sim: Simulation) -> dict:
    world = sim.world()
    world["__penalties__"] = sim.penalties
    world["__last_error__"] = sim.last_error
    return world


def _check_dsl_invariants(program: Program, simulation: Simulation,
                          interpreter: Interpreter | None = None) -> list[str]:
    interpreter = interpreter or Interpreter(program)
    world = _world_for_invariants(simulation)
    violations = []
    for invariant in program.invariants:
        try:
            if not bool(interpreter.eval(invariant.expr, world)):
                violations.append(f"{invariant.name}: {invariant.message}")
        except EvalError as exc:
            violations.append(f"{invariant.name}: evaluation error {exc}")
    return violations


def _random_walk(program: Program, seed: int, steps: int = 14) -> Simulation:
    rng = random.Random(seed)
    sim = Simulation.from_program(program)
    operations = ["reserve", "start_rental", "return_scooter", "advance",
                  "service_done", "claim_damage", "refund_deposit", "pay_penalty",
                  "cancel_reservation", "expire_reservation", "report_lost"]
    for _ in range(steps):
        op = rng.choice(operations)
        if op == "advance":
            sim.apply(op, minutes=rng.choice([0, 1, 5, 15, 16, 60, 1440, 1500, 3000]))
        elif op == "service_done":
            sim.apply(op, operator=None)
        elif op == "cancel_reservation":
            sim.apply(op)
        else:
            sim.apply(op)
    return sim


# ------------------------------------------------------------------ property 1
def property_no_forbidden_transition(program: Program, seeds: Iterable[int] = range(12)
                                     ) -> PropertyResult:
    allowed = _allowed(program)
    violations: list[str] = []
    checks = 0
    for seed in seeds:
        sim = _random_walk(program, seed)
        for machine, src, dst, event in sim.transitions:
            checks += 1
            if (machine, src, dst, event) not in allowed:
                violations.append(
                    f"seed {seed}: forbidden {machine} {src} -> {dst} on {event}")
    # exhaustive check that every declared edge is well formed
    for machine, src, dst, event in sorted(allowed):
        checks += 1
        if not machine or not src or not dst or not event:
            violations.append(f"incomplete transition {machine} {src} {dst} {event}")
    return PropertyResult("no_forbidden_transition", not violations,
                          violations[:10], checks)


# ------------------------------------------------------------------ property 2
def property_invariants_hold(program: Program, seeds: Iterable[int] = range(12)
                             ) -> PropertyResult:
    interpreter = Interpreter(program)
    violations: list[str] = []
    checks = 0
    for seed in seeds:
        sim = Simulation.from_program(program)
        rng = random.Random(seed * 31 + 7)
        for _ in range(12):
            op = rng.choice(["reserve", "start_rental", "advance", "return_scooter",
                             "pay_penalty", "claim_damage", "service_done"])
            if op == "advance":
                sim.apply(op, minutes=rng.choice([0, 10, 1440, 1500, 3000]))
            elif op == "service_done":
                sim.apply(op, operator=None)
            else:
                sim.apply(op)
            checks += 1
            for item in sim.check_invariants():
                violations.append(f"seed {seed}: {item}")
            for item in _check_dsl_invariants(program, sim, interpreter):
                violations.append(f"seed {seed}: {item}")
    return PropertyResult("invariants_hold", not violations, violations[:10], checks)


# ------------------------------------------------------------------ property 3
def property_idempotent_return(program: Program) -> PropertyResult:
    violations: list[str] = []
    checks = 0
    sim = Simulation.from_program(program)
    sim.customer["deposit"] = int(sim.tariff["depositAmount"]) + 1000
    sim.apply("reserve")
    sim.apply("start_rental")
    sim.apply("advance", minutes=2000)
    first = sim.apply("return_scooter")
    checks += 1
    if not first.ok:
        violations.append("first return failed")
    penalties_before = len(sim.penalties)
    debt_before = sim.customer["debt"]
    state_before = sim.scooter["state"]
    second = sim.apply("return_scooter")
    checks += 3
    if len(sim.penalties) != penalties_before:
        violations.append("repeated return created another penalty")
    if sim.customer["debt"] != debt_before:
        violations.append("repeated return changed the debt")
    if sim.scooter["state"] != state_before:
        violations.append("repeated return changed the scooter state")
    if not second.ok or not second.data.get("idempotent"):
        violations.append("repeated return is not marked idempotent")

    # reservation expiry is idempotent as well
    sim2 = Simulation.from_program(program)
    sim2.apply("reserve")
    sim2.apply("advance", minutes=int(sim2.tariff["reservationTtl"]) + 1)
    first_expiry = sim2.apply("expire_reservation")
    second_expiry = sim2.apply("expire_reservation")
    checks += 4
    if not first_expiry.ok or not second_expiry.ok:
        violations.append("expiry failed")
    if not second_expiry.data.get("idempotent"):
        violations.append("second expiry is not idempotent")
    if sim2.scooter["state"] != "available":
        violations.append("expiry did not free the scooter")

    # paying penalties twice does not double charge
    if int(sim.customer["debt"]) > 0:
        payments_before = len(sim.payments)
        first_pay = sim.apply("pay_penalty")
        count_after_first = len(sim.payments)
        second_pay = sim.apply("pay_penalty")
        checks += 3
        if count_after_first <= payments_before:
            violations.append("first payment did not record a payment")
        if len(sim.payments) != count_after_first:
            violations.append("repeated payment created another payment")
        if not first_pay.ok or not second_pay.ok:
            violations.append("payment failed")
    return PropertyResult("idempotent_return", not violations, violations, checks)


# ------------------------------------------------------------------ property 4
def property_no_privilege_leak(program: Program) -> PropertyResult:
    violations: list[str] = []
    checks = 0
    actor_params = {
        "reserve": "customer", "start_rental": "customer",
        "cancel_reservation": "customer", "return_scooter": "customer",
        "report_lost": "customer", "claim_damage": "customer",
        "refund_deposit": "customer", "pay_penalty": "customer",
        "expire_reservation": "customer", "service_done": "operator",
        "block_customer": "operator", "unblock_customer": "operator",
        "grant_role": "admin", "advance": "minutes",
    }
    from .ops import OPS
    record_key = {"customer": "customer", "operator": "operator", "admin": "admin"}
    for role in ("Customer", "Operator", "Admin"):
        for op, signature in sorted(OPS.items()):
            param = actor_params.get(op)
            if param is None or param == "minutes":
                continue
            sim = Simulation.from_program(program)
            base_record = sim.records[record_key[param]]
            actor = {key: value for key, value in base_record.items()}
            actor["role"] = role
            kwargs = {param: actor}
            if op == "grant_role":
                kwargs["role"] = "Customer"
            result = sim.apply(op, **kwargs)
            checks += 1
            allowed = signature.permission in sim.permissions_for(role)
            leaked = (result.error != "E_PERMISSION") if not allowed else (
                result.error == "E_PERMISSION")
            if leaked:
                violations.append(
                    f"role {role} op {op}: allowed={allowed}, error={result.error!r}")
    if not violations:
        # customer must not be able to grant an admin role
        sim = Simulation.from_program(program)
        admin = {key: value for key, value in sim.customer.items()}
        result = sim.apply("grant_role", admin=admin, customer=sim.customer,
                           role="Admin")
        checks += 1
        if result.error != "E_PERMISSION":
            violations.append("customer managed to grant a role")
    return PropertyResult("no_privilege_leak", not violations, violations, checks)


# ------------------------------------------------------------------ property 5
def property_fee_and_deadlines(program: Program) -> PropertyResult:
    violations: list[str] = []
    checks = 0
    sim = Simulation.from_program(program)
    tariff = sim.tariff
    grace = int(tariff["graceMinutes"])
    hourly = int(tariff["lateFeePerHour"])
    for minutes_late in list(range(0, 121)) + [130, 200, 1000, 1439, 1440,
                                               1441, 2880, 5000]:
        checks += 2
        expected = 0 if minutes_late <= grace else (
            math.ceil((minutes_late - grace) / 60) * hourly)
        actual = sim.late_fee(minutes_late)
        if actual != expected:
            violations.append(
                f"late {minutes_late}: fee {actual}, expected {expected}")
        hours = sim.late_hours(minutes_late)
        if hours != (0 if minutes_late <= grace else
                     math.ceil((minutes_late - grace) / 60)):
            violations.append(f"late {minutes_late}: wrong hour count {hours}")

    # the DSL rule must agree with the runtime formula
    interpreter = Interpreter(program)
    rule = program.rule("BRI-04")
    if rule is not None:
        for minutes_late in (0, 9, 10, 11, 70, 130, 1000):
            world = sim.world()
            world["rental"]["minutesLate"] = minutes_late
            world["rental"]["lateFee"] = 0
            try:
                interpreter.evaluate_rule("BRI-04", world)
            except EvalError as exc:
                violations.append(f"rule BRI-04 failed: {exc}")
                continue
            checks += 1
            if int(world["rental"]["lateFee"]) != sim.late_fee(minutes_late):
                violations.append(
                    f"rule and engine disagree at {minutes_late} minutes")

    # deadlines
    checks += 1
    if sim.claim_deadline(0) != int(tariff["damageClaimHours"]) * 60:
        violations.append("claim deadline is not 48 hours")
    checks += 1
    deadline = sim.refund_deadline(0)  # Thursday
    business_days = 0
    cursor = 0
    while cursor < deadline:
        cursor += 1440
        if sim.weekday(cursor) < 5:
            business_days += 1
    if business_days != int(tariff["refundBusinessDays"]):
        violations.append(f"refund deadline covers {business_days} business days")
    checks += 1
    if sim.price_multiplier(0) != 100:
        violations.append("January must use the base coefficient")
    from ..runtime.engine import EPOCH
    from datetime import datetime
    may = int((datetime(2026, 5, 1) - EPOCH).total_seconds() // 60)
    checks += 1
    if sim.price_multiplier(may) != int(sim.season["coefficient"]):
        violations.append("May must use the seasonal coefficient")
    return PropertyResult("fee_and_deadlines", not violations, violations, checks)


# ------------------------------------------------------------------ property 6
def property_reservation_expiry(program: Program) -> PropertyResult:
    violations: list[str] = []
    checks = 0
    sim = Simulation.from_program(program)
    ttl = int(sim.tariff["reservationTtl"])
    deposit = int(sim.tariff["depositAmount"]) + 1000
    at_limit = Simulation.from_program(program)
    at_limit.customer["deposit"] = deposit
    at_limit.apply("reserve")
    at_limit.apply("advance", minutes=ttl)
    result = at_limit.apply("start_rental")
    checks += 1
    if not result.ok:
        violations.append(f"start at TTL {ttl} failed: {result.error}")

    past_limit = Simulation.from_program(program)
    past_limit.customer["deposit"] = deposit
    past_limit.apply("reserve")
    past_limit.apply("advance", minutes=ttl + 1)
    result = past_limit.apply("start_rental")
    checks += 1
    if result.error != "E_RESERVATION_EXPIRED":
        violations.append(f"start at TTL+1 returned {result.error!r}")
    checks += 1
    if past_limit.scooter["state"] != "available":
        violations.append("expired reservation did not release the scooter")
    checks += 1
    if int(past_limit.reservation["expiresAt"]) - int(
            past_limit.reservation["createdAt"]) != ttl:
        violations.append("reservation TTL is not stored on the reservation")
    return PropertyResult("reservation_expiry", not violations, violations, checks)


# ------------------------------------------------------------------ property 7
def property_maintenance_threshold(program: Program) -> PropertyResult:
    violations: list[str] = []
    checks = 0
    sim = Simulation.from_program(program)
    limit = int(sim.tariff["serviceMileage"])
    deposit = int(sim.tariff["depositAmount"]) + 1000
    below = Simulation.from_program(program)
    below.customer["deposit"] = deposit
    below.scooter["mileageSinceService"] = limit - 1
    checks += 1
    if not below.apply("reserve").ok:
        violations.append("scooter below the service limit was rejected")
    at_limit = Simulation.from_program(program)
    at_limit.customer["deposit"] = deposit
    at_limit.scooter["mileageSinceService"] = limit
    checks += 1
    if at_limit.apply("reserve").error != "E_MAINTENANCE_DUE":
        violations.append("scooter at the service limit was not rejected")
    crossing = Simulation.from_program(program)
    crossing.customer["deposit"] = deposit
    crossing.scooter["mileageSinceService"] = limit - 10
    crossing.rental["distanceKm"] = 10
    crossing.apply("reserve")
    crossing.apply("start_rental")
    crossing.apply("return_scooter")
    checks += 2
    if crossing.scooter["state"] != "maintenance":
        violations.append("return crossing the limit did not enter maintenance")
    if not crossing.maintenance:
        violations.append("no maintenance record was created")
    return PropertyResult("maintenance_threshold", not violations, violations, checks)


# ------------------------------------------------------------------ property 8
def property_money_conservation(program: Program) -> PropertyResult:
    violations: list[str] = []
    checks = 0
    sim = Simulation.from_program(program)
    sim.customer["deposit"] = int(sim.tariff["depositAmount"]) + 1000
    sim.apply("reserve")
    sim.apply("start_rental")
    sim.apply("advance", minutes=3000)
    sim.apply("return_scooter")
    checks += 1
    penalty_sum = sum(int(p["amount"]) for p in sim.penalties)
    if int(sim.customer["debt"]) != penalty_sum:
        violations.append(
            f"debt {sim.customer['debt']} != penalties {penalty_sum}")
    for penalty in sim.penalties:
        checks += 1
        if int(penalty["amount"]) < 0:
            violations.append("negative penalty")
    sim.apply("pay_penalty")
    checks += 3
    if int(sim.customer["debt"]) != 0:
        violations.append("debt is not cleared after payment")
    paid = sum(int(p["amount"]) for p in sim.payments)
    if paid != penalty_sum:
        violations.append(f"paid {paid} != penalties {penalty_sum}")
    if sim.check_invariants():
        violations.append("invariants broken: " + "; ".join(sim.check_invariants()))
    checks += 1
    if int(sim.customer["deposit"]) < 0:
        violations.append("deposit went negative")

    # refund returns the deposit exactly once
    before = sum(int(p["amount"]) for p in sim.payments)
    refund = sim.apply("refund_deposit")
    checks += 2
    if not refund.ok:
        violations.append(f"refund failed: {refund.error}")
    elif sum(int(p["amount"]) for p in sim.payments) != before + int(
            refund.data.get("amount", 0)):
        violations.append("refund payment amount mismatch")
    second = sim.apply("refund_deposit")
    checks += 1
    if second.ok and int(second.data.get("amount", 0)) != 0:
        violations.append("second refund paid the deposit again")
    return PropertyResult("money_conservation", not violations, violations, checks)


PROPERTIES = [
    property_no_forbidden_transition,
    property_invariants_hold,
    property_idempotent_return,
    property_no_privilege_leak,
    property_fee_and_deadlines,
    property_reservation_expiry,
    property_maintenance_threshold,
    property_money_conservation,
]


def check_all(program: Program) -> dict:
    results = [prop(program) for prop in PROPERTIES]
    return {
        "ok": all(result.ok for result in results),
        "results": [result.to_dict() for result in results],
    }
