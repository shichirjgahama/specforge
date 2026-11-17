"""Operation catalogue shared by semantic analysis and the runtime engine.

Each operation has typed parameters, a permission name and a short description.
Keeping this table in one place guarantees that the type checker and the
interpreter agree about the accepted calls.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpSignature:
    name: str
    params: tuple[tuple[str, str], ...]
    permission: str
    description: str


OPS: dict[str, OpSignature] = {
    "reserve": OpSignature("reserve", (("customer", "Customer"), ("scooter", "Scooter")),
                           "reserve", "create a reservation for a scooter"),
    "start_rental": OpSignature("start_rental", (("customer", "Customer"), ("scooter", "Scooter")),
                                "rent", "start a rental from an active reservation"),
    "cancel_reservation": OpSignature("cancel_reservation", (("customer", "Customer"), ("scooter", "Scooter")),
                                      "reserve", "cancel an active reservation"),
    "return_scooter": OpSignature("return_scooter", (("customer", "Customer"), ("scooter", "Scooter")),
                                  "return", "return a rented scooter"),
    "report_lost": OpSignature("report_lost", (("customer", "Customer"), ("scooter", "Scooter")),
                               "report", "report a scooter as lost"),
    "service_done": OpSignature("service_done", (("operator", "Operator"), ("scooter", "Scooter")),
                                "service", "finish maintenance and return to service"),
    "block_customer": OpSignature("block_customer", (("operator", "Operator"), ("customer", "Customer")),
                                  "block", "block a customer account"),
    "unblock_customer": OpSignature("unblock_customer", (("operator", "Operator"), ("customer", "Customer")),
                                    "block", "unblock a customer account"),
    "claim_damage": OpSignature("claim_damage", (("customer", "Customer"), ("rental", "Rental")),
                                "claim", "register a damage claim for a closed rental"),
    "refund_deposit": OpSignature("refund_deposit", (("customer", "Customer"),),
                                  "refund", "refund the deposit after a closed rental"),
    "pay_penalty": OpSignature("pay_penalty", (("customer", "Customer"),),
                               "pay", "pay outstanding penalties"),
    "advance": OpSignature("advance", (("minutes", "Int"),),
                           "advance", "move the simulation clock forward"),
    "expire_reservation": OpSignature("expire_reservation", (("customer", "Customer"),),
                                      "reserve", "force reservation expiry check"),
    "grant_role": OpSignature("grant_role", (("admin", "Admin"), ("customer", "Customer"), ("role", "Text")),
                              "grant", "assign a role to a customer"),
}

PERMISSIONS = sorted({op.permission for op in OPS.values()})

# Operation name -> transition events it is allowed to trigger in a state
# machine. Return can either close a clean rental or move a scooter to
# maintenance, start_rental reopens a closed rental record, and so on.
EVENT_ALIASES: dict[str, set[str]] = {
    "reserve": {"reserve"},
    "start_rental": {"start", "reopen", "rent"},
    "return_scooter": {"return", "returnFault", "close"},
    "report_lost": {"lost"},
    "service_done": {"service"},
    "cancel_reservation": {"cancel"},
    "expire_reservation": {"expire"},
}
