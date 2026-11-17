"""Runtime tests: scenarios, generated tests, determinism, properties."""
import pytest

from specforge.core.interpreter import Interpreter
from specforge.core.properties import PROPERTIES, check_all
from specforge.runtime.codegen import generate_tests
from specforge.runtime.engine import Simulation
from specforge.runtime.runner import Runner, run_tests


def test_all_dsl_scenarios_execute(program, semantic):
    interpreter = Interpreter(program, semantic.model)
    results = interpreter.run_all_scenarios()
    assert len(results) >= 6
    for result in results:
        assert result.ok, (result.name, result.failures,
                           result.invariant_violations,
                           result.transition_violations, result.error)
        assert not result.transition_violations


def test_generated_suite_has_sixty_cases_in_three_groups(cases):
    assert len(cases) == 60
    assert sum(1 for c in cases if c.kind == "scenario") == 20
    assert sum(1 for c in cases if c.kind == "boundary") == 20
    assert sum(1 for c in cases if c.kind == "property") == 20
    assert all(c.requirements for c in cases)
    assert all(c.nodes for c in cases)
    assert len({c.id for c in cases}) == 60


def test_generated_suite_passes(program, cases):
    summary = run_tests(program, cases)
    assert summary.failed == 0, [
        (result.test_id, result.message) for result in summary.results
        if result.status == "failed"
    ]
    assert summary.passed == 60


def test_runner_is_bit_for_bit_deterministic(program, cases, tmp_path):
    first = run_tests(program, cases)
    second = run_tests(program, cases)
    assert first.digest == second.digest
    assert first.report_json() == second.report_json()
    assert [r.status for r in first.results] == [r.status for r in second.results]
    path_a = tmp_path / "run_a.json"
    path_b = tmp_path / "run_b.json"
    path_a.write_text(first.report_json(), encoding="utf-8")
    path_b.write_text(second.report_json(), encoding="utf-8")
    assert path_a.read_bytes() == path_b.read_bytes()


def test_test_generation_is_deterministic(program, index):
    first = generate_tests(program, index)
    second = generate_tests(program, index)
    assert [case.to_dict() for case in first] == [case.to_dict() for case in second]
    assert [case.id for case in first] == [f"T-{n:03d}" for n in range(1, 61)]


def test_eight_properties_hold(program):
    report = check_all(program)
    assert len(PROPERTIES) == 8
    assert report["ok"], [item for item in report["results"] if not item["ok"]]
    assert len(report["results"]) == 8
    assert all(item["checks"] > 0 for item in report["results"])


def test_late_fee_formula_and_grace(program):
    sim = Simulation.from_program(program)
    grace = int(sim.tariff["graceMinutes"])
    hourly = int(sim.tariff["lateFeePerHour"])
    assert sim.late_fee(grace) == 0
    assert sim.late_fee(grace + 1) == hourly
    assert sim.late_fee(grace + 60) == hourly
    assert sim.late_fee(grace + 61) == 2 * hourly
    assert sim.late_hours(grace + 61) == 2


def test_engine_rejects_forbidden_state_changes(program):
    sim = Simulation.from_program(program)
    result = sim.apply("start_rental")
    assert result.error == "E_NO_RESERVATION"
    assert sim.scooter["state"] == "available"
    assert sim.check_invariants() == []


def test_engine_permissions(program):
    sim = Simulation.from_program(program)
    customer = sim.customer
    result = sim.apply("service_done", operator=customer)
    assert result.error == "E_PERMISSION"
    result = sim.apply("grant_role", admin=customer, customer=customer, role="Admin")
    assert result.error == "E_PERMISSION"


def test_engine_return_is_idempotent(program):
    sim = Simulation.from_program(program)
    sim.apply("reserve")
    sim.apply("start_rental")
    sim.apply("advance", minutes=2000)
    first = sim.apply("return_scooter")
    penalties = len(sim.penalties)
    debt = sim.customer["debt"]
    second = sim.apply("return_scooter")
    assert first.ok and second.ok
    assert second.data["idempotent"] is True
    assert len(sim.penalties) == penalties
    assert sim.customer["debt"] == debt


def test_reservation_ttl_boundary(program):
    exactly = Simulation.from_program(program)
    exactly.apply("reserve")
    exactly.apply("advance", minutes=15)
    assert exactly.apply("start_rental").ok

    late = Simulation.from_program(program)
    late.apply("reserve")
    late.apply("advance", minutes=16)
    assert late.apply("start_rental").error == "E_RESERVATION_EXPIRED"
    assert late.scooter["state"] == "available"


def test_dsl_rule_matches_engine_formula(program):
    sim = Simulation.from_program(program)
    interpreter = Interpreter(program)
    for minutes_late in (0, 10, 11, 70, 130):
        world = sim.world()
        world["rental"]["minutesLate"] = minutes_late
        world["rental"]["lateFee"] = 0
        interpreter.evaluate_rule("BRI-04", world)
        assert world["rental"]["lateFee"] == sim.late_fee(minutes_late)


def test_full_run_is_under_ten_seconds(program, cases):
    summary = run_tests(program, cases)
    assert summary.duration_ms < 10_000
