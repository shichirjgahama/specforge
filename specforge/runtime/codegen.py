"""Deterministic test generation.

60 test cases:
  T-001..T-020  scenario tests from user stories
  T-021..T-040  boundary tests around thresholds and deadlines
  T-041..T-060  property based generated inputs with fixed seeds

Every test stores its requirement links, the specification nodes it exercises
and a literal expectation captured from the reference model. Literal
expectations are what make impact analysis meaningful: after a threshold
change only tests that depend on the changed nodes fail.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..core.nodes import SpecIndex
from .engine import EPOCH, Simulation, apply_step


@dataclass
class TestCase:
    id: str
    kind: str
    title: str
    requirements: tuple[str, ...]
    nodes: tuple[str, ...]
    setup: dict
    steps: list[dict]
    expected: dict
    seed: int = 0
    source: str = "generated"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "title": self.title,
            "requirements": list(self.requirements), "nodes": list(self.nodes),
            "setup": self.setup, "steps": self.steps, "expected": self.expected,
            "seed": self.seed, "source": self.source,
        }

    @staticmethod
    def from_dict(data: dict) -> "TestCase":
        return TestCase(
            id=data["id"], kind=data["kind"], title=data["title"],
            requirements=tuple(data.get("requirements", ())),
            nodes=tuple(data.get("nodes", ())),
            setup=data.get("setup", {}), steps=data.get("steps", []),
            expected=data.get("expected", {}), seed=data.get("seed", 0),
            source=data.get("source", "generated"),
        )


def op(name: str, **args) -> dict:
    return {"op": name, "args": args}


def minutes_at(year: int, month: int, day: int) -> int:
    return int((datetime(year, month, day) - EPOCH).total_seconds() // 60)


@dataclass
class _Spec:
    title: str
    reqs: tuple[str, ...]
    setup: dict = field(default_factory=dict)
    steps: list[dict] = field(default_factory=list)
    capture: tuple[str, ...] = ()
    expect_error: Optional[str] = None
    rules: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    seed: int = 0
    invariants: bool = True


SPECIAL_PATHS = {
    "season.multiplier": lambda sim: sim.price_multiplier(),
    "refund.deadline": lambda sim: sim.refund_deadline(sim.now),
    "claim.deadline": lambda sim: sim.claim_deadline(int(sim.rental["returnedAt"])),
    "late.hours": lambda sim: sim.late_hours(int(sim.rental["minutesLate"])),
    "maintenance.count": lambda sim: len(sim.maintenance),
}


SCENARIO_SPECS: list[_Spec] = [
    _Spec("Happy path: reserve, rent, return", ("R-001", "R-002", "R-003"),
          {"customer.deposit": 3000, "scooter.battery": 90},
          [op("reserve"), op("start_rental"), op("advance", minutes=55),
           op("return_scooter")],
          ("scooter.state", "rental.state", "customer.debt", "penalty.count"),
          rules=("BRI-01", "BRI-03", "BRI-04"), events=("reserve", "rent", "return")),
    _Spec("Cancel a reservation", ("R-017",),
          {}, [op("reserve"), op("cancel_reservation")],
          ("scooter.state", "reservation.state"),
          rules=("BRI-01",), events=("reserve", "cancel")),
    _Spec("Reservation expires before rental start", ("R-015", "R-002"),
          {}, [op("reserve"), op("advance", minutes=16), op("start_rental")],
          ("scooter.state", "reservation.state"), expect_error="E_RESERVATION_EXPIRED",
          rules=("BRI-02", "BRI-03"), events=("reserve", "expire")),
    _Spec("Rental start without reservation", ("R-020", "R-014"),
          {}, [op("start_rental")], ("scooter.state",),
          expect_error="E_NO_RESERVATION", rules=("BRI-12",)),
    _Spec("Low battery is rejected", ("R-005",),
          {"scooter.battery": 19}, [op("reserve")], ("scooter.state",),
          expect_error="E_BATTERY_LOW", rules=("BRI-01",), events=(),
          fields=("Scooter.battery",)),
    _Spec("Battery exactly at the limit is accepted", ("R-005",),
          {"scooter.battery": 20}, [op("reserve")], ("scooter.state", "reservation.state"),
          rules=("BRI-01",), events=("reserve",), fields=("Scooter.battery",)),
    _Spec("Deposit below the minimum is rejected", ("R-004",),
          {"customer.deposit": 2999}, [op("reserve")], ("scooter.state",),
          expect_error="E_DEPOSIT_LOW", rules=("BRI-01",), fields=("Customer.deposit",)),
    _Spec("Deposit exactly at the minimum is accepted", ("R-004",),
          {"customer.deposit": 3000}, [op("reserve")], ("scooter.state",),
          rules=("BRI-01",), events=("reserve",), fields=("Customer.deposit",)),
    _Spec("Maintenance threshold rejects the scooter", ("R-006",),
          {"scooter.mileageSinceService": 500}, [op("reserve")], ("scooter.state",),
          expect_error="E_MAINTENANCE_DUE", rules=("BRI-01",),
          fields=("Scooter.mileageSinceService",)),
    _Spec("Mileage below the threshold is accepted", ("R-006",),
          {"scooter.mileageSinceService": 499}, [op("reserve")], ("scooter.state",),
          rules=("BRI-01",), events=("reserve",),
          fields=("Scooter.mileageSinceService",)),
    _Spec("One active rental per customer", ("R-014",),
          {}, [op("reserve"), op("start_rental"), op("reserve")],
          ("scooter.state", "rental.state"), expect_error="E_ACTIVE_RENTAL",
          rules=("BRI-01", "BRI-12"), events=("reserve", "rent")),
    _Spec("Late fee for 70 minutes late", ("R-007",),
          {}, [op("reserve"), op("start_rental"), op("advance", minutes=1510),
               op("return_scooter")],
          ("rental.minutesLate", "rental.lateFee", "customer.debt", "penalty.count"),
          rules=("BRI-04",), events=("reserve", "rent", "markOverdue", "close")),
    _Spec("Grace period: 10 minutes late is free", ("R-007",),
          {}, [op("reserve"), op("start_rental"), op("advance", minutes=1450),
               op("return_scooter")],
          ("rental.minutesLate", "rental.lateFee", "penalty.count"),
          rules=("BRI-04",), events=("reserve", "rent", "markOverdue", "close")),
    _Spec("Grace plus one minute costs one hour", ("R-007",),
          {}, [op("reserve"), op("start_rental"), op("advance", minutes=1451),
               op("return_scooter")],
          ("rental.minutesLate", "rental.lateFee", "penalty.count"),
          rules=("BRI-04",), events=("reserve", "rent", "markOverdue", "close")),
    _Spec("Extremely overdue customer is blocked", ("R-008",),
          {}, [op("reserve"), op("start_rental"), op("advance", minutes=3000),
               op("return_scooter")],
          ("customer.status", "customer.lateReturns", "rental.lateFee"),
          rules=("BRI-04", "BRI-05"), events=("reserve", "rent", "markOverdue", "close")),
    _Spec("Three late returns trigger the blacklist", ("R-009",),
          {}, [op("reserve"), op("start_rental"), op("advance", minutes=1500),
               op("return_scooter"), op("reserve"), op("start_rental"),
               op("advance", minutes=1500), op("return_scooter"), op("reserve"),
               op("start_rental"), op("advance", minutes=1500), op("return_scooter")],
          ("customer.lateReturns", "customer.status", "penalty.count"),
          rules=("BRI-04", "BRI-06"), events=("reserve", "rent", "markOverdue", "close")),
    _Spec("Lost scooter is charged and blocks the customer", ("R-010",),
          {}, [op("reserve"), op("start_rental"), op("report_lost")],
          ("scooter.state", "customer.status", "penalty.total", "rental.state"),
          rules=("BRI-07",), events=("reserve", "rent", "lost", "close")),
    _Spec("Damage claim inside the window", ("R-011",),
          {}, [op("reserve"), op("start_rental"), op("return_scooter"),
               op("advance", minutes=100), op("claim_damage")],
          ("rental.state",), rules=("BRI-08",),
          events=("reserve", "rent", "return", "close")),
    _Spec("Damage claim after the window", ("R-011",),
          {}, [op("reserve"), op("start_rental"), op("return_scooter"),
               op("advance", minutes=2940), op("claim_damage")],
          ("rental.state",), expect_error="E_CLAIM_LATE", rules=("BRI-08",),
          events=("reserve", "rent", "return", "close")),
    _Spec("Service returns the scooter to the pool", ("R-016", "R-006"),
          {"scooter.mileageSinceService": 490},
          [op("reserve"), op("start_rental"), op("return_scooter"),
           op("service_done", operator=None)],
          ("scooter.state", "scooter.mileageSinceService", "scooter.battery"),
          rules=("BRI-11",), events=("reserve", "rent", "returnFault", "service")),
]


BOUNDARY_SPECS: list[_Spec] = [
    _Spec("Battery 19 is below the minimum", ("R-005",), {"scooter.battery": 19},
          [op("reserve")], ("scooter.state",), expect_error="E_BATTERY_LOW",
          rules=("BRI-01",), fields=("Scooter.battery",)),
    _Spec("Battery 20 is the minimum", ("R-005",), {"scooter.battery": 20},
          [op("reserve")], ("scooter.state",), rules=("BRI-01",),
          events=("reserve",), fields=("Scooter.battery",)),
    _Spec("Blocked customer cannot reserve", ("R-018",),
          {"customer.status": "blocked"}, [op("reserve")], ("scooter.state",),
          expect_error="E_CUSTOMER_BLOCKED", rules=("BRI-01",),
          fields=("Customer.status",)),
    _Spec("Mileage 499 is rentable", ("R-006",),
          {"scooter.mileageSinceService": 499}, [op("reserve")],
          ("scooter.state",), rules=("BRI-01",), events=("reserve",),
          fields=("Scooter.mileageSinceService",)),
    _Spec("Mileage 500 needs service", ("R-006",),
          {"scooter.mileageSinceService": 500}, [op("reserve")],
          ("scooter.state",), expect_error="E_MAINTENANCE_DUE", rules=("BRI-01",),
          fields=("Scooter.mileageSinceService",)),
    _Spec("Deposit 2999 is rejected", ("R-004",), {"customer.deposit": 2999},
          [op("reserve")], ("scooter.state",), expect_error="E_DEPOSIT_LOW",
          rules=("BRI-01",), fields=("Customer.deposit",)),
    _Spec("Deposit 3000 is accepted", ("R-004",), {"customer.deposit": 3000},
          [op("reserve")], ("scooter.state",), rules=("BRI-01",),
          events=("reserve",), fields=("Customer.deposit",)),
    _Spec("Late 10 minutes is inside the grace", ("R-007",),
          {}, [op("reserve"), op("start_rental"), op("advance", minutes=1450),
               op("return_scooter")],
          ("rental.lateFee", "late.hours"), rules=("BRI-04",),
          events=("reserve", "rent", "markOverdue", "close")),
    _Spec("Late 11 minutes starts the first hour", ("R-007",),
          {}, [op("reserve"), op("start_rental"), op("advance", minutes=1451),
               op("return_scooter")],
          ("rental.lateFee", "late.hours"), rules=("BRI-04",),
          events=("reserve", "rent", "markOverdue", "close")),
    _Spec("Late 130 minutes starts the second hour", ("R-007",),
          {}, [op("reserve"), op("start_rental"), op("advance", minutes=1570),
               op("return_scooter")],
          ("rental.lateFee", "late.hours"), rules=("BRI-04",),
          events=("reserve", "rent", "markOverdue", "close")),
    _Spec("Reservation is valid at exactly 15 minutes", ("R-015",),
          {}, [op("reserve"), op("advance", minutes=15), op("start_rental")],
          ("rental.state", "scooter.state"), rules=("BRI-02", "BRI-03"),
          events=("reserve", "rent")),
    _Spec("Reservation expired at 16 minutes", ("R-015",),
          {}, [op("reserve"), op("advance", minutes=16), op("start_rental")],
          ("scooter.state", "reservation.state"), expect_error="E_RESERVATION_EXPIRED",
          rules=("BRI-02", "BRI-03"), events=("reserve", "expire")),
    _Spec("Damage claim exactly at 48 hours", ("R-011",),
          {}, [op("reserve"), op("start_rental"), op("return_scooter"),
               op("advance", minutes=2880), op("claim_damage")],
          ("rental.state",), rules=("BRI-08",),
          events=("reserve", "rent", "return", "close")),
    _Spec("Damage claim 48 hours and 1 minute", ("R-011",),
          {}, [op("reserve"), op("start_rental"), op("return_scooter"),
               op("advance", minutes=2881), op("claim_damage")],
          ("rental.state",), expect_error="E_CLAIM_LATE", rules=("BRI-08",),
          events=("reserve", "rent", "return", "close")),
    _Spec("April 30 uses the base price", ("R-013",),
          {"now": minutes_at(2026, 4, 30)}, [op("advance", minutes=0)],
          ("season.multiplier",), rules=("BRI-10",), fields=("Season.coefficient",)),
    _Spec("May 1 uses the seasonal price", ("R-013",),
          {"now": minutes_at(2026, 5, 1)}, [op("advance", minutes=0)],
          ("season.multiplier",), rules=("BRI-10",), fields=("Season.coefficient",)),
    _Spec("Refund deadline skips the weekend", ("R-012",),
          {}, [op("reserve"), op("start_rental"), op("return_scooter"),
               op("refund_deposit")],
          ("refund.deadline", "payment.total"), rules=("BRI-09",),
          events=("reserve", "rent", "return", "close"), fields=("Payment.amount",)),
    _Spec("Battery can reach zero after a return", ("R-003", "R-005"),
          {"scooter.battery": 100, "rental.batteryUsed": 100},
          [op("reserve"), op("start_rental"), op("return_scooter")],
          ("scooter.battery", "scooter.state"), events=("reserve", "rent", "return")),
    _Spec("Two late returns stay below the blacklist", ("R-009",),
          {}, [op("reserve"), op("start_rental"), op("advance", minutes=1500),
               op("return_scooter"), op("reserve"), op("start_rental"),
               op("advance", minutes=1500), op("return_scooter")],
          ("customer.lateReturns", "customer.status"), rules=("BRI-04", "BRI-06"),
          events=("reserve", "rent", "markOverdue", "close")),
    _Spec("Operator blocks and unblocks a customer", ("R-019",),
          {}, [op("block_customer"), op("unblock_customer")],
          ("customer.status",), fields=("Customer.status",)),
]


FIELD_OF_PATH = {
    "scooter": "Scooter", "rental": "Rental", "customer": "Customer",
    "reservation": "Reservation", "penalty": "Penalty", "payment": "Payment",
    "tariff": "Tariff", "season": "Season", "operator": "Operator",
    "station": "Station", "damageClaim": "DamageClaim",
    "maintenanceRecord": "MaintenanceRecord", "blacklistEntry": "BlacklistEntry",
}

ERROR_RULES = {
    "E_BATTERY_LOW": ("BRI-01",),
    "E_MAINTENANCE_DUE": ("BRI-01",),
    "E_DEPOSIT_LOW": ("BRI-01",),
    "E_ACTIVE_RENTAL": ("BRI-12",),
    "E_RESERVATION_EXPIRED": ("BRI-02", "BRI-03"),
    "E_NO_RESERVATION": ("BRI-03",),
    "E_CUSTOMER_BLOCKED": ("BRI-01",),
    "E_CLAIM_LATE": ("BRI-08",),
    "E_CLAIM_WINDOW": ("BRI-08",),
}

EVENT_RULES = {
    "reserve": ("BRI-01", "BRI-02"),
    "cancel": ("BRI-01",),
    "expire": ("BRI-02", "BRI-03"),
    "rent": ("BRI-03", "BRI-12"),
    "start": ("BRI-03", "BRI-12"),
    "reopen": ("BRI-12",),
    "return": ("BRI-04", "BRI-11"),
    "returnFault": ("BRI-04", "BRI-11"),
    "close": ("BRI-04",),
    "markOverdue": ("BRI-05",),
    "lost": ("BRI-07",),
    "service": ("BRI-11",),
    "retire": ("BRI-11",),
    "dispute": ("BRI-08",),
    "resolve": ("BRI-08",),
}


class TestGenerator:
    def __init__(self, program, index: SpecIndex, seed: int = 1234) -> None:
        self.program = program
        self.index = index
        self.seed = seed
        self._transition_by_event: dict[str, list[str]] = {}
        for node in index.nodes.values():
            if node.kind == "transition":
                event = node.detail.get("event", "")
                self._transition_by_event.setdefault(event, []).append(node.id)

    def generate(self) -> list[TestCase]:
        specs: list[tuple[str, _Spec, int]] = []
        for spec in SCENARIO_SPECS:
            specs.append(("scenario", spec, 0))
        for spec in BOUNDARY_SPECS:
            specs.append(("boundary", spec, 0))
        for seed in range(1, 21):
            specs.append(("property", self._property_spec(seed), seed))
        if len(specs) != 60:
            raise RuntimeError(f"expected 60 tests, built {len(specs)}")
        cases: list[TestCase] = []
        for number, (kind, spec, seed) in enumerate(specs, start=1):
            cases.append(self._build(f"T-{number:03d}", kind, spec, seed))
        return cases

    # ------------------------------------------------------------- building
    def _build(self, test_id: str, kind: str, spec: _Spec, seed: int) -> TestCase:
        sim = Simulation.from_program(self.program)
        for path, value in spec.setup.items():
            if path == "now":
                sim.now = int(value)
            else:
                sim.set_path(path, value)
        for step in spec.steps:
            apply_step(sim, step)

        values: dict[str, Any] = {}
        for path in spec.capture:
            if path in SPECIAL_PATHS:
                values[path] = SPECIAL_PATHS[path](sim)
            else:
                values[path] = sim.get_path(path)
        if spec.expect_error is not None and sim.last_error != spec.expect_error:
            raise RuntimeError(
                f"{test_id} ({spec.title}): expected {spec.expect_error}, "
                f"reference model produced {sim.last_error!r}")
        expected = {
            "error": spec.expect_error if spec.expect_error is not None else sim.last_error,
            "values": values,
            "invariants": "clean" if spec.invariants else "skip",
        }
        nodes = self._nodes(spec, sim, values)
        return TestCase(
            id=test_id, kind=kind, title=spec.title,
            requirements=spec.reqs, nodes=tuple(sorted(nodes)),
            setup=spec.setup, steps=spec.steps, expected=expected,
            seed=seed,
        )

    def _nodes(self, spec: _Spec, sim: Simulation, values: dict) -> set[str]:
        nodes: set[str] = set()
        for rule in spec.rules:
            nodes.add(f"rule:{rule}")
        for event in spec.events:
            for node_id in self._transition_by_event.get(event, ()):
                nodes.add(node_id)
        for event in {t[3] for t in sim.transitions}:
            for node_id in self._transition_by_event.get(event, ()):
                nodes.add(node_id)
            for rule in EVENT_RULES.get(event, ()):
                nodes.add(f"rule:{rule}")
        if sim.last_error in ERROR_RULES:
            for rule in ERROR_RULES[sim.last_error]:
                nodes.add(f"rule:{rule}")

        # every test checks all DSL invariants after execution
        for invariant in self.program.invariants:
            node_id = f"invariant:{invariant.name}"
            if node_id in self.index.nodes:
                nodes.add(node_id)

        minutes_late = int(sim.rental["minutesLate"])
        if minutes_late > 0:
            nodes.add("rule:BRI-04")
            nodes.add("rule:BRI-06")
        if minutes_late > int(sim.tariff["overdueBlockHours"]) * 60:
            nodes.add("rule:BRI-05")
        if int(sim.customer["lateReturns"]) >= 2:
            nodes.add("rule:BRI-06")
        if int(sim.customer["rentals"]) >= 1:
            nodes.add("rule:BRI-12")
        if any("status" in path for path in spec.capture):
            nodes.add("rule:BRI-05")
            nodes.add("rule:BRI-06")
        if sim.maintenance or int(sim.scooter["mileageSinceService"]) >= int(
                sim.tariff["serviceMileage"]):
            nodes.add("rule:BRI-11")

        field_paths = list(spec.fields)
        for path in list(spec.setup):
            if path == "now" or "." not in path:
                continue
            field_paths.append(path)
        for path in list(spec.capture) + list(values):
            if "." in path:
                field_paths.append(path)
        for path in field_paths:
            entity, _, field_name = path.partition(".")
            entity_name = FIELD_OF_PATH.get(entity)
            if entity_name and field_name:
                node_id = f"field:{entity_name}.{field_name}"
                if node_id in self.index.nodes:
                    nodes.add(node_id)
        # keep only real nodes
        return {node_id for node_id in nodes if node_id in self.index.nodes}

    # ------------------------------------------------------------ property
    def _property_spec(self, seed: int) -> _Spec:
        rng = random.Random(seed * 7919)
        mode = seed % 4
        if mode == 0:
            # validation paths intentionally include invalid inputs
            battery = rng.choice([0, 5, 19, 20, 21, 55, 80, 100])
            deposit = rng.choice([0, 1500, 2999, 3000, 3001, 5000])
            mileage = rng.choice([0, 120, 499, 500, 501, 620])
        else:
            battery = rng.choice([20, 21, 55, 80, 90, 100])
            deposit = rng.choice([3000, 3001, 3500, 5000])
            mileage = 490 if mode == 3 else rng.choice([0, 120, 499])
        setup = {
            "scooter.battery": battery,
            "customer.deposit": deposit,
            "scooter.mileageSinceService": mileage,
        }
        late = rng.randrange(0, 3000)
        if mode == 0:
            steps = [op("reserve"), op("advance", minutes=late)]
            capture = ("scooter.state", "reservation.state")
            events = ("reserve",)
            reqs = ("R-005", "R-014")
        elif mode == 1:
            steps = [op("reserve"), op("start_rental"), op("return_scooter")]
            capture = ("scooter.state", "rental.state")
            events = ("reserve", "rent", "return")
            reqs = ("R-001", "R-002", "R-003")
        elif mode == 2:
            steps = [op("reserve"), op("start_rental"), op("advance", minutes=late),
                     op("return_scooter")]
            capture = ("rental.lateFee", "rental.minutesLate", "customer.debt")
            events = ("reserve", "rent", "markOverdue", "close")
            reqs = ("R-007", "R-009")
        else:
            steps = [op("reserve"), op("start_rental"),
                     op("advance", minutes=rng.randrange(0, 60)),
                     op("return_scooter"), op("service_done", operator=None)]
            capture = ("scooter.state", "scooter.mileageSinceService")
            events = ("reserve", "rent", "returnFault", "service")
            reqs = ("R-006", "R-016")
        return _Spec(
            title=f"Property scenario seed {seed}: battery={battery}, deposit={deposit}, "
                  f"mileage={mileage}, late={late}",
            reqs=reqs, setup=setup, steps=steps,
            capture=capture, rules=("BRI-01",), events=events, seed=seed,
        )


def generate_tests(program, index: SpecIndex, seed: int = 1234) -> list[TestCase]:
    return TestGenerator(program, index, seed).generate()
