"""Demo change requests with different change types."""
from __future__ import annotations

from ..core.impact import ChangeRequest


def seed_change_requests() -> list[ChangeRequest]:
    return [
        ChangeRequest(
            id="CR-001",
            title="Shorten the late fee grace period to 5 minutes",
            kind="rule_threshold",
            description=(
                "Support reports that customers exploit the 10 minute grace period. "
                "The grace period becomes 5 minutes, the hourly fee stays 500. "
                "Requirement R-007 is updated with the new threshold."
            ),
            spec_edits=[{
                "find": "const graceMinutes: Int = 10;",
                "replace": "const graceMinutes: Int = 5;",
            }],
            requirement_edits=[{
                "id": "R-007",
                "criteria_add": [
                    "CR-001: the grace period is 5 minutes starting from version 2.",
                    "CR-001: 6 minutes late costs 500 rubles.",
                ],
                "notes": "Grace period reduced by CR-001.",
            }],
            target_nodes=("const:graceMinutes",),
            status="open",
        ),
        ChangeRequest(
            id="CR-002",
            title="Raise the minimum rental battery to 25 percent",
            kind="rule_threshold",
            description=(
                "Winter failures show that 20 percent is not enough to reach a station. "
                "The minimum battery becomes 25 percent for reservation and rental start."
            ),
            spec_edits=[{
                "find": "const minBattery: Int = 20;",
                "replace": "const minBattery: Int = 25;",
            }],
            requirement_edits=[{
                "id": "R-005",
                "criteria_add": [
                    "CR-002: battery 24 percent is rejected.",
                    "CR-002: battery 25 percent is accepted.",
                ],
                "notes": "Minimum battery raised by CR-002.",
            }],
            target_nodes=("const:minBattery",),
            status="open",
        ),
        ChangeRequest(
            id="CR-003",
            title="Shorten the damage claim window to 24 hours",
            kind="rule_threshold",
            description=(
                "The insurer accepts claims only within one day. The claim window "
                "changes from 48 to 24 hours and requirement R-011 is updated."
            ),
            spec_edits=[{
                "find": "const damageClaimHours: Int = 48;",
                "replace": "const damageClaimHours: Int = 24;",
            }],
            requirement_edits=[{
                "id": "R-011",
                "criteria_add": [
                    "CR-003: a claim 24 hours and 1 minute after return is rejected.",
                ],
                "notes": "Claim window reduced by CR-003.",
            }],
            target_nodes=("const:damageClaimHours",),
            status="open",
        ),
        ChangeRequest(
            id="CR-004",
            title="Add a helmet deposit field to Rental",
            kind="entity_structure",
            description=(
                "A separate helmet deposit is introduced in the data model. "
                "The change is structural: it must be propagated to all tests that "
                "touch the Rental entity, even though behaviour stays the same."
            ),
            spec_edits=[{
                "find": "  tariffId: Text;",
                "replace": "  tariffId: Text;\n  helmetDeposit: Money >= 0 = 0;",
            }],
            requirement_edits=[{
                "id": "R-003",
                "criteria_add": [
                    "CR-004: the rental record stores the helmet deposit separately.",
                ],
            }],
            target_nodes=("field:Rental.tariffId",),
            status="open",
        ),
        ChangeRequest(
            id="CR-005",
            title="Clarify the return wording without changing behaviour",
            kind="requirement_text",
            description=(
                "Editorial change: requirement R-003 explains that the rental closes "
                "immediately after the return. No rule changes, tests must stay green."
            ),
            spec_edits=[],
            requirement_edits=[{
                "id": "R-003",
                "story": "As a customer I want to return a scooter at any station so that "
                         "the rental closes immediately and the scooter becomes available "
                         "for the next customer.",
                "criteria_add": [
                    "CR-005: the rental closes immediately after the return event.",
                ],
            }],
            target_nodes=(),
            status="open",
        ),
    ]
