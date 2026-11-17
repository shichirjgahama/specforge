"""Runtime for the scooter sharing domain.

The engine is the executable part of the specification:
  * state transitions for Scooter and Rental
  * time based business rules (reservation TTL, late fees, claim window,
    refund deadline, seasonal price, blacklist window)
  * permissions per role
  * safety invariants

All money is integer rubles, all time is integer minutes from 2026-01-01
00:00. The virtual clock makes test runs deterministic.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from ..core import ast_nodes as A
from ..core.ops import OPS


EPOCH = datetime(2026, 1, 1, 0, 0)
MINUTES_PER_DAY = 24 * 60

DEFAULT_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "Customer": {"reserve", "rent", "return", "pay", "claim", "refund", "report"},
    "Operator": {"service", "block", "return", "reserve"},
    "Admin": {"reserve", "rent", "return", "pay", "claim", "refund", "report",
              "service", "block", "grant"},
}

CONFIG_MAP = {
    "lateFeePerHour": ("tariff", "lateFeePerHour"),
    "graceMinutes": ("tariff", "graceMinutes"),
    "depositAmount": ("tariff", "depositAmount"),
    "maxRentalHours": ("tariff", "maxHours"),
    "perMinutePrice": ("tariff", "perMinute"),
    "minBattery": ("tariff", "minBattery"),
    "serviceMileage": ("tariff", "serviceMileage"),
    "reservationTtlMinutes": ("tariff", "reservationTtl"),
    "damageClaimHours": ("tariff", "damageClaimHours"),
    "refundBusinessDays": ("tariff", "refundBusinessDays"),
    "blacklistLateReturns": ("tariff", "blacklistLateReturns"),
    "blacklistWindowDays": ("tariff", "blacklistWindowDays"),
    "seasonCoefficient": ("season", "coefficient"),
    "lostFee": ("tariff", "lostFee"),
    "overdueBlockHours": ("tariff", "overdueBlockHours"),
    "blockDays": ("tariff", "blockDays"),
    "seasonStartMonth": ("season", "startMonth"),
    "seasonEndMonth": ("season", "endMonth"),
}

DEFAULT_RECORDS: dict[str, dict[str, Any]] = {
    "customer": {
        "id": "C-1", "name": "Test Customer", "role": "Customer",
        "status": "active", "deposit": 3000, "debt": 0, "balance": 0,
        "lateReturns": 0, "lateEvents": [], "blockedUntil": 0,
        "trustScore": 100, "rentals": 0,
    },
    "operator": {"id": "OP-1", "name": "Test Operator", "role": "Operator", "status": "active"},
    "admin": {"id": "AD-1", "name": "Test Admin", "role": "Admin", "status": "active"},
    "scooter": {
        "id": "S-1", "model": "City-1", "state": "available", "battery": 100,
        "mileageSinceService": 0, "station": "ST-1", "reservedUntil": 0,
        "lastServiceAt": 0,
    },
    "station": {"id": "ST-1", "name": "Central", "capacity": 20, "occupied": 1},
    "reservation": {
        "id": "RS-1", "state": "none", "createdAt": 0, "expiresAt": 0,
    },
    "rental": {
        "id": "RT-1", "state": "draft", "startedAt": 0, "dueAt": 0,
        "returnedAt": 0, "distanceKm": 10, "batteryUsed": 10,
        "minutesLate": 0, "lateFee": 0, "closed": False, "tariffId": "TR-1",
    },
    "tariff": {
        "id": "TR-1", "name": "City", "perMinute": 10, "depositAmount": 3000,
        "lateFeePerHour": 500, "graceMinutes": 10, "maxHours": 24,
        "minBattery": 20, "serviceMileage": 500, "reservationTtl": 15,
        "damageClaimHours": 48, "refundBusinessDays": 3,
        "blacklistLateReturns": 3, "blacklistWindowDays": 30,
        "lostFee": 25000, "overdueBlockHours": 24, "blockDays": 7,
    },
    "season": {"id": "SE-1", "name": "High", "coefficient": 130,
               "startMonth": 5, "endMonth": 9},
    "penalty": {"id": "PN-1", "amount": 0, "reason": "", "createdAt": 0,
                "paid": False, "rentalId": ""},
    "payment": {"id": "PY-1", "amount": 0, "kind": "rent", "createdAt": 0,
                "status": "done", "rentalId": ""},
    "damageClaim": {"id": "DC-1", "amount": 1000, "severity": "minor",
                    "state": "none", "createdAt": 0, "rentalId": ""},
    "maintenanceRecord": {"id": "MR-1", "kind": "scheduled", "startedAt": 0,
                          "finishedAt": 0},
    "blacklistEntry": {"id": "BL-1", "reason": "", "createdAt": 0, "expiresAt": 0},
}


@dataclass
class DomainError(Exception):
    code: str
    message: str
    detail: dict = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.code}: {self.message}"


@dataclass
class OpResult:
    ok: bool
    op: str
    error: str = ""
    message: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "op": self.op, "error": self.error,
                "message": self.message, "data": self.data}


def apply_step(sim: "Simulation", step: dict) -> OpResult:
    """Apply a test step, dropping None arguments so engine defaults apply."""
    args = {key: value for key, value in (step.get("args") or {}).items()
            if value is not None}
    return sim.apply(step["op"], **args)


class Simulation:
    """A single scenario world with one instance of each domain entity."""

    def __init__(self, program: Optional[A.Program] = None,
                 config: Optional[dict] = None,
                 now: int = 0) -> None:
        self.now = now
        self.records: dict[str, dict[str, Any]] = copy.deepcopy(DEFAULT_RECORDS)
        self.penalties: list[dict] = []
        self.payments: list[dict] = []
        self.maintenance: list[dict] = []
        self.blacklist: list[dict] = []
        self.claims: list[dict] = []
        self.transitions: list[tuple[str, str, str, str]] = []  # machine, src, dst, event
        self.audit: list[dict] = []
        self.program = program
        self.last_error = ""
        self.last_result: Optional[OpResult] = None
        self.role_permissions = self._build_permissions(program)
        self._apply_config(config or {})
        self._apply_program_config(program)

    # ------------------------------------------------------------- factories
    @classmethod
    def from_program(cls, program: Optional[A.Program], config: Optional[dict] = None,
                     now: int = 0) -> "Simulation":
        return cls(program=program, config=config, now=now)

    def clone(self) -> "Simulation":
        clone = Simulation(program=self.program, now=self.now)
        clone.records = copy.deepcopy(self.records)
        clone.penalties = copy.deepcopy(self.penalties)
        clone.payments = copy.deepcopy(self.payments)
        clone.maintenance = copy.deepcopy(self.maintenance)
        clone.blacklist = copy.deepcopy(self.blacklist)
        clone.claims = copy.deepcopy(self.claims)
        clone.transitions = list(self.transitions)
        clone.audit = list(self.audit)
        clone.last_error = self.last_error
        clone.role_permissions = {k: set(v) for k, v in self.role_permissions.items()}
        clone.last_result = self.last_result
        return clone

    def _build_permissions(self, program: Optional[A.Program]) -> dict[str, set[str]]:
        result = {role: set(perms) for role, perms in DEFAULT_ROLE_PERMISSIONS.items()}
        if program is None:
            return result
        result = {}
        for role in program.roles:
            may = set(role.may) - set(role.forbid)
            result[role.name] = may
        for role, perms in DEFAULT_ROLE_PERMISSIONS.items():
            result.setdefault(role, set(perms))
        return result

    def _apply_program_config(self, program: Optional[A.Program]) -> None:
        if program is None:
            return
        values: dict[str, Any] = {}
        for const in program.consts:
            value = self._const_value(const.value, values)
            values[const.name] = value
        for const_name, (entity, key) in CONFIG_MAP.items():
            value = values.get(const_name)
            if isinstance(value, int):
                self.records[entity][key] = value

    @staticmethod
    def _const_value(expr: A.Expr, known: dict) -> Any:
        if isinstance(expr, A.Literal):
            return expr.value
        if isinstance(expr, A.Name):
            return known.get(expr.name)
        if isinstance(expr, A.Unary) and expr.op == "-":
            inner = Simulation._const_value(expr.operand, known)
            return -inner if isinstance(inner, int) else inner
        return None

    def _apply_config(self, config: dict) -> None:
        for key, value in config.items():
            if key == "now":
                self.now = int(value)
                continue
            if "." in key:
                entity, _, field_name = key.partition(".")
                if entity in self.records and field_name in self.records[entity]:
                    self.records[entity][field_name] = value
                continue
            if key in self.records:
                if isinstance(value, dict):
                    self.records[key].update(value)
                continue
            target = CONFIG_MAP.get(key)
            if target:
                entity, field_name = target
                self.records[entity][field_name] = value

    # ---------------------------------------------------------------- access
    @property
    def customer(self) -> dict:
        return self.records["customer"]

    @property
    def scooter(self) -> dict:
        return self.records["scooter"]

    @property
    def rental(self) -> dict:
        return self.records["rental"]

    @property
    def reservation(self) -> dict:
        return self.records["reservation"]

    @property
    def tariff(self) -> dict:
        return self.records["tariff"]

    @property
    def season(self) -> dict:
        return self.records["season"]

    def world(self) -> dict[str, Any]:
        world: dict[str, Any] = {name: record for name, record in self.records.items()}
        world["now"] = self.now
        # maintenanceRecord and blacklistEntry are also aliases used by rules
        world["maintenanceRecord"] = self.maintenance[-1] if self.maintenance else self.records["maintenanceRecord"]
        world["blacklistEntry"] = self.blacklist[-1] if self.blacklist else self.records["blacklistEntry"]
        world["damageClaim"] = self.claims[-1] if self.claims else self.records["damageClaim"]
        return world

    def get_path(self, path: str) -> Any:
        if path == "now":
            return self.now
        if path == "penalty.total":
            return sum(int(p.get("amount", 0)) for p in self.penalties)
        if path == "penalty.count":
            return len(self.penalties)
        if path == "payment.total":
            return sum(int(p.get("amount", 0)) for p in self.payments)
        if path == "maintenance.count":
            return len(self.maintenance)
        if path == "lastError":
            return self.last_error
        if path == "last.ok":
            return self.last_result.ok if self.last_result else None
        base, _, field_name = path.partition(".")
        record = self.records.get(base)
        if record is None:
            raise KeyError(f"unknown path {path!r}")
        if field_name and field_name not in record:
            raise KeyError(f"unknown field {path!r}")
        return record.get(field_name) if field_name else dict(record)

    def set_path(self, path: str, value: Any) -> None:
        if path == "now":
            self.now = int(value)
            return
        base, _, field_name = path.partition(".")
        if base not in self.records or field_name not in self.records[base]:
            raise KeyError(f"cannot set unknown path {path!r}")
        self.records[base][field_name] = value

    # ----------------------------------------------------------------- time
    def datetime(self, minutes: Optional[int] = None) -> datetime:
        return EPOCH + timedelta(minutes=self.now if minutes is None else minutes)

    def weekday(self, minutes: Optional[int] = None) -> int:
        return self.datetime(minutes).weekday()

    def is_high_season(self, minutes: Optional[int] = None) -> bool:
        month = self.datetime(minutes).month
        return self.season["startMonth"] <= month <= self.season["endMonth"]

    def price_multiplier(self, minutes: Optional[int] = None) -> int:
        return int(self.season["coefficient"]) if self.is_high_season(minutes) else 100

    def rental_cost(self, minutes: int, at: Optional[int] = None) -> int:
        base = int(self.tariff["perMinute"]) * max(0, minutes)
        return base * self.price_multiplier(at) // 100

    def late_fee(self, minutes_late: int) -> int:
        if minutes_late <= int(self.tariff["graceMinutes"]):
            return 0
        billable = minutes_late - int(self.tariff["graceMinutes"])
        hours = (billable + 59) // 60
        return hours * int(self.tariff["lateFeePerHour"])

    def late_hours(self, minutes_late: int) -> int:
        if minutes_late <= int(self.tariff["graceMinutes"]):
            return 0
        return (minutes_late - int(self.tariff["graceMinutes"]) + 59) // 60

    def refund_deadline(self, closed_at: int) -> int:
        days = int(self.tariff["refundBusinessDays"])
        current = closed_at
        added = 0
        while added < days:
            current += MINUTES_PER_DAY
            if self.weekday(current) < 5:
                added += 1
        return current

    def claim_deadline(self, returned_at: int) -> int:
        return returned_at + int(self.tariff["damageClaimHours"]) * 60

    # ----------------------------------------------------------- permissions
    def permissions_for(self, role: str) -> set[str]:
        return set(self.role_permissions.get(role, set()))

    def _check_permission(self, actor: dict, op: str) -> None:
        if op == "advance":
            return
        permission = OPS[op].permission if op in OPS else op
        role = actor.get("role", "")
        if permission not in self.permissions_for(role):
            raise DomainError("E_PERMISSION",
                              f"role {role} has no permission {permission!r}",
                              {"op": op, "role": role})

    # ------------------------------------------------------------------ audit
    def _audit(self, actor: str, action: str, detail: dict) -> None:
        entry = {"at": self.now, "actor": actor, "action": action,
                 "detail": detail}
        self.audit.append(entry)

    def _set_state(self, entity: str, machine_field: str, value: str, event: str) -> None:
        old = self.records[entity].get(machine_field)
        self.records[entity][machine_field] = value
        machine = {"scooter": "ScooterState", "rental": "RentalState",
                   "reservation": "ReservationState"}.get(entity, entity)
        self.transitions.append((machine, str(old), value, event))

    # ------------------------------------------------------------- operations
    def apply(self, op: str, **kwargs) -> OpResult:
        self.last_error = ""
        try:
            handler = getattr(self, f"_op_{op}", None)
            if handler is None:
                raise DomainError("E_UNKNOWN_OP", f"unknown operation {op!r}")
            result = handler(**kwargs)
            self.last_result = result
            return result
        except DomainError as exc:
            self.last_error = exc.code
            result = OpResult(False, op, error=exc.code, message=exc.message,
                              data=exc.detail)
            self.last_result = result
            return result

    def _ok(self, op: str, **data) -> OpResult:
        return OpResult(True, op, data=data)

    # reserve ---------------------------------------------------------------
    def _op_reserve(self, customer: Optional[dict] = None,
                    scooter: Optional[dict] = None, **_) -> OpResult:
        customer = customer or self.customer
        scooter = scooter or self.scooter
        self._check_permission(customer, "reserve")
        self._ensure_active_customer(customer)
        self._ensure_no_active_rental(customer)
        if scooter["state"] != "available":
            raise DomainError("E_SCOOTER_BUSY",
                              f"scooter {scooter['id']} is {scooter['state']}")
        self._ensure_scooter_usable(scooter)
        if int(customer["deposit"]) < int(self.tariff["depositAmount"]):
            raise DomainError("E_DEPOSIT_LOW",
                              f"deposit {customer['deposit']} is below "
                              f"{self.tariff['depositAmount']}")

        self._set_state("scooter", "state", "reserved", "reserve")
        scooter["reservedUntil"] = self.now + int(self.tariff["reservationTtl"])
        self.reservation.update({
            "id": "RS-1", "state": "active", "createdAt": self.now,
            "expiresAt": scooter["reservedUntil"],
        })
        self._audit(customer.get("id", ""), "reserve", {"scooter": scooter["id"]})
        return self._ok("reserve", scooterState="reserved",
                        expiresAt=scooter["reservedUntil"])

    def _op_cancel_reservation(self, customer: Optional[dict] = None,
                               scooter: Optional[dict] = None, **_) -> OpResult:
        customer = customer or self.customer
        scooter = scooter or self.scooter
        self._check_permission(customer, "reserve")
        if scooter["state"] != "reserved":
            raise DomainError("E_NO_RESERVATION", "scooter is not reserved")
        self._set_state("scooter", "state", "available", "cancel")
        scooter["reservedUntil"] = 0
        self.reservation["state"] = "cancelled"
        return self._ok("cancel_reservation", scooterState="available")

    def _op_expire_reservation(self, customer: Optional[dict] = None,
                               scooter: Optional[dict] = None, **_) -> OpResult:
        customer = customer or self.customer
        scooter = scooter or self.scooter
        if self.reservation["state"] != "active":
            return self._ok("expire_reservation", expired=False,
                            scooterState=scooter["state"], idempotent=True)
        if self.now <= int(self.reservation["expiresAt"]):
            return self._ok("expire_reservation", expired=False,
                            scooterState=scooter["state"])
        self._set_state("scooter", "state", "available", "expire")
        scooter["reservedUntil"] = 0
        self.reservation["state"] = "expired"
        return self._ok("expire_reservation", expired=True,
                        scooterState="available", idempotent=True)

    # rental ----------------------------------------------------------------
    def _op_start_rental(self, customer: Optional[dict] = None,
                         scooter: Optional[dict] = None, **_) -> OpResult:
        customer = customer or self.customer
        scooter = scooter or self.scooter
        self._check_permission(customer, "rent")
        self._ensure_active_customer(customer)
        self._ensure_no_active_rental(customer)
        if scooter["state"] != "reserved":
            raise DomainError("E_NO_RESERVATION", "scooter is not reserved")
        if self.reservation["state"] != "active":
            raise DomainError("E_NO_RESERVATION", "reservation is not active")
        if self.now > int(self.reservation["expiresAt"]):
            self._set_state("scooter", "state", "available", "expire")
            self.reservation["state"] = "expired"
            raise DomainError("E_RESERVATION_EXPIRED",
                              "reservation TTL has expired")
        self._ensure_scooter_usable(scooter)
        if int(customer["deposit"]) < int(self.tariff["depositAmount"]):
            raise DomainError("E_DEPOSIT_LOW", "deposit is too low")

        self._set_state("scooter", "state", "rented", "rent")
        self.reservation["state"] = "used"
        reopen = self.rental["state"] == "closed"
        self._set_state("rental", "state", "active", "reopen" if reopen else "start")
        self.rental.update({
            "startedAt": self.now,
            "dueAt": self.now + int(self.tariff["maxHours"]) * 60,
            "returnedAt": 0, "minutesLate": 0, "lateFee": 0, "closed": False,
            "distanceKm": self.rental.get("distanceKm", 10),
        })
        customer["rentals"] = int(customer.get("rentals", 0)) + 1
        self._audit(customer.get("id", ""), "start_rental",
                    {"scooter": scooter["id"], "rental": "RT-1"})
        return self._ok("start_rental", scooterState="rented",
                        rentalState="active", dueAt=self.rental["dueAt"])

    def _op_return_scooter(self, customer: Optional[dict] = None,
                           scooter: Optional[dict] = None, **_) -> OpResult:
        customer = customer or self.customer
        scooter = scooter or self.scooter
        self._check_permission(customer, "return")
        if self.rental["closed"]:
            # idempotent: a repeated return does not create charges
            return self._ok("return_scooter", scooterState=scooter["state"],
                            rentalState=self.rental["state"],
                            fee=self.rental["lateFee"],
                            penaltyTotal=sum(p["amount"] for p in self.penalties),
                            idempotent=True)
        if self.rental["state"] not in ("active", "overdue"):
            raise DomainError("E_NOT_RENTED", "there is no active rental")

        due_at = int(self.rental["dueAt"])
        minutes_late = max(0, self.now - due_at)
        fee = self.late_fee(minutes_late)
        self.rental["minutesLate"] = minutes_late
        self.rental["lateFee"] = fee
        self.rental["returnedAt"] = self.now
        self.rental["closed"] = True
        if minutes_late > 0 and self.rental["state"] == "active":
            self._set_state("rental", "state", "overdue", "markOverdue")
        self._set_state("rental", "state", "closed", "close")

        if fee > 0:
            penalty = {
                "id": f"PN-{len(self.penalties) + 1}",
                "amount": fee, "reason": "late_return", "createdAt": self.now,
                "paid": False, "rentalId": self.rental["id"],
            }
            self.penalties.append(penalty)
            customer["debt"] = int(customer["debt"]) + fee
            self._audit(customer.get("id", ""), "penalty", {"amount": fee})

        if minutes_late > 0:
            customer["lateReturns"] = int(customer["lateReturns"]) + 1
            customer.setdefault("lateEvents", []).append(self.now)
            window_start = self.now - int(self.tariff["blacklistWindowDays"]) * MINUTES_PER_DAY
            recent = [t for t in customer["lateEvents"] if t >= window_start]
            customer["lateEvents"] = recent
            if len(recent) >= int(self.tariff["blacklistLateReturns"]):
                customer["status"] = "blocked"
                customer["blockedUntil"] = self.now + int(self.tariff["blockDays"]) * MINUTES_PER_DAY
                for entry in self.blacklist:
                    if entry["expiresAt"] > self.now:
                        break
                else:
                    self.blacklist.append({
                        "id": f"BL-{len(self.blacklist) + 1}",
                        "reason": "late_returns", "createdAt": self.now,
                        "expiresAt": customer["blockedUntil"],
                    })

        if minutes_late > int(self.tariff["overdueBlockHours"]) * 60:
            customer["status"] = "blocked"
            customer["blockedUntil"] = max(
                int(customer.get("blockedUntil", 0)),
                self.now + int(self.tariff["blockDays"]) * MINUTES_PER_DAY,
            )

        distance = int(self.rental.get("distanceKm", 0))
        scooter["mileageSinceService"] = int(scooter["mileageSinceService"]) + distance
        battery_used = int(self.rental.get("batteryUsed", 10))
        scooter["battery"] = max(0, int(scooter["battery"]) - battery_used)

        next_state = "maintenance" if int(scooter["mileageSinceService"]) >= int(
            self.tariff["serviceMileage"]) else "available"
        self._set_state("scooter", "state", next_state,
                        "returnFault" if next_state == "maintenance" else "return")
        scooter["reservedUntil"] = 0
        if next_state == "maintenance":
            self.maintenance.append({
                "id": f"MR-{len(self.maintenance) + 1}", "kind": "scheduled",
                "startedAt": self.now, "finishedAt": 0,
            })
        self._audit(customer.get("id", ""), "return_scooter",
                    {"fee": fee, "scooterState": next_state})
        return self._ok("return_scooter", scooterState=next_state,
                        rentalState="closed", fee=fee,
                        penaltyTotal=sum(p["amount"] for p in self.penalties),
                        minutesLate=minutes_late)

    def _op_report_lost(self, customer: Optional[dict] = None,
                        scooter: Optional[dict] = None, **_) -> OpResult:
        customer = customer or self.customer
        scooter = scooter or self.scooter
        self._check_permission(customer, "report")
        if self.rental["state"] != "active":
            raise DomainError("E_NOT_RENTED", "lost can only be reported during a rental")
        fee = int(self.tariff["lostFee"])
        self.penalties.append({
            "id": f"PN-{len(self.penalties) + 1}", "amount": fee,
            "reason": "lost_scooter", "createdAt": self.now, "paid": False,
            "rentalId": self.rental["id"],
        })
        customer["debt"] = int(customer["debt"]) + fee
        customer["status"] = "blocked"
        customer["blockedUntil"] = self.now + 30 * MINUTES_PER_DAY
        self.rental["closed"] = True
        self._set_state("rental", "state", "closed", "close")
        self.rental["returnedAt"] = self.now
        self._set_state("scooter", "state", "lost", "lost")
        return self._ok("report_lost", penalty=fee, scooterState="lost")

    def _op_service_done(self, operator: Optional[dict] = None,
                         scooter: Optional[dict] = None, **_) -> OpResult:
        operator = operator or self.records["operator"]
        scooter = scooter or self.scooter
        self._check_permission(operator, "service")
        if scooter["state"] != "maintenance":
            raise DomainError("E_INVALID_STATE", "scooter is not in maintenance")
        self._set_state("scooter", "state", "available", "service")
        scooter["mileageSinceService"] = 0
        scooter["battery"] = 100
        scooter["lastServiceAt"] = self.now
        if self.maintenance:
            self.maintenance[-1]["finishedAt"] = self.now
        return self._ok("service_done", scooterState="available")

    # account ---------------------------------------------------------------
    def _op_block_customer(self, operator: Optional[dict] = None,
                           customer: Optional[dict] = None, **_) -> OpResult:
        operator = operator or self.records["operator"]
        customer = customer or self.customer
        self._check_permission(operator, "block")
        customer["status"] = "blocked"
        customer["blockedUntil"] = self.now + int(self.tariff["blockDays"]) * MINUTES_PER_DAY
        return self._ok("block_customer", status="blocked")

    def _op_unblock_customer(self, operator: Optional[dict] = None,
                             customer: Optional[dict] = None, **_) -> OpResult:
        operator = operator or self.records["operator"]
        customer = customer or self.customer
        self._check_permission(operator, "block")
        customer["status"] = "active"
        customer["blockedUntil"] = 0
        return self._ok("unblock_customer", status="active")

    def _op_claim_damage(self, customer: Optional[dict] = None,
                         rental: Optional[dict] = None, **_) -> OpResult:
        customer = customer or self.customer
        rental = rental or self.rental
        self._check_permission(customer, "claim")
        if not rental["closed"]:
            raise DomainError("E_NOT_CLOSED", "damage claim needs a closed rental")
        if self.now > self.claim_deadline(int(rental["returnedAt"])):
            raise DomainError("E_CLAIM_LATE",
                              f"claim window of {self.tariff['damageClaimHours']}h expired")
        claim = {
            "id": f"DC-{len(self.claims) + 1}",
            "amount": int(self.records["damageClaim"]["amount"]),
            "severity": self.records["damageClaim"].get("severity", "minor"),
            "state": "open", "createdAt": self.now, "rentalId": rental["id"],
        }
        self.claims.append(claim)
        return self._ok("claim_damage", claimId=claim["id"], amount=claim["amount"])

    def _op_refund_deposit(self, customer: Optional[dict] = None, **_) -> OpResult:
        customer = customer or self.customer
        self._check_permission(customer, "refund")
        if self._has_active_rental(customer):
            raise DomainError("E_ACTIVE_RENTAL", "cannot refund during an active rental")
        unpaid = [p for p in self.penalties if not p.get("paid")]
        if unpaid:
            raise DomainError("E_ACTIVE_PENALTY",
                              "refund is blocked by unpaid penalties")
        amount = int(customer["deposit"])
        if amount < 0:
            raise DomainError("E_INVALID_STATE", "deposit cannot be negative")
        closed_at = int(self.rental["returnedAt"]) if self.rental["closed"] else self.now
        deadline = self.refund_deadline(closed_at)
        customer["deposit"] = 0
        self.payments.append({
            "id": f"PY-{len(self.payments) + 1}", "amount": amount,
            "kind": "deposit_refund", "createdAt": self.now,
            "status": "done", "rentalId": self.rental["id"],
        })
        return self._ok("refund_deposit", amount=amount, deadline=deadline)

    def _op_pay_penalty(self, customer: Optional[dict] = None, **_) -> OpResult:
        customer = customer or self.customer
        self._check_permission(customer, "pay")
        unpaid = [p for p in self.penalties if not p.get("paid")]
        total = sum(int(p["amount"]) for p in unpaid)
        for penalty in unpaid:
            penalty["paid"] = True
        customer["debt"] = max(0, int(customer["debt"]) - total)
        if total:
            self.payments.append({
                "id": f"PY-{len(self.payments) + 1}", "amount": total,
                "kind": "penalty", "createdAt": self.now,
                "status": "done", "rentalId": self.rental["id"],
            })
        return self._ok("pay_penalty", paid=total, debt=customer["debt"])

    def _op_grant_role(self, admin: Optional[dict] = None,
                       customer: Optional[dict] = None, role: str = "Customer",
                       **_) -> OpResult:
        admin = admin or self.records["admin"]
        customer = customer or self.customer
        self._check_permission(admin, "grant")
        before = customer.get("role", "Customer")
        customer["role"] = role
        self._audit(admin.get("id", ""), "grant_role",
                    {"customer": customer.get("id"), "from": before, "to": role})
        return self._ok("grant_role", role=role)

    def _op_advance(self, minutes: int = 0, **_) -> OpResult:
        self.now += int(minutes)
        return self._ok("advance", now=self.now)

    # ---------------------------------------------------------- preconditions
    def _ensure_active_customer(self, customer: dict) -> None:
        if customer.get("status") != "active":
            raise DomainError("E_CUSTOMER_BLOCKED",
                              f"customer status is {customer.get('status')!r}")
        until = int(customer.get("blockedUntil", 0))
        if until and self.now < until:
            raise DomainError("E_CUSTOMER_BLOCKED",
                              "customer is temporarily blocked")

    def _ensure_scooter_usable(self, scooter: dict) -> None:
        if int(scooter["battery"]) < int(self.tariff["minBattery"]):
            raise DomainError("E_BATTERY_LOW",
                              f"battery {scooter['battery']}% is below "
                              f"{self.tariff['minBattery']}%")
        if int(scooter["mileageSinceService"]) >= int(self.tariff["serviceMileage"]):
            raise DomainError("E_MAINTENANCE_DUE",
                              f"mileage {scooter['mileageSinceService']} reached "
                              f"service threshold {self.tariff['serviceMileage']}")

    def _has_active_rental(self, customer: dict) -> bool:
        return bool(self.rental["state"] in ("active", "overdue") and not self.rental["closed"])

    def _ensure_no_active_rental(self, customer: dict) -> None:
        if self._has_active_rental(customer):
            raise DomainError("E_ACTIVE_RENTAL", "customer already has an active rental")

    # ------------------------------------------------------------- invariants
    def check_invariants(self) -> list[str]:
        violations: list[str] = []
        if int(self.customer.get("deposit", 0)) < 0:
            violations.append("deposit cannot be negative")
        if int(self.customer.get("debt", 0)) < 0:
            violations.append("debt cannot be negative")
        battery = int(self.scooter.get("battery", 0))
        if not 0 <= battery <= 100:
            violations.append("scooter battery must stay in 0..100")
        if int(self.scooter.get("mileageSinceService", 0)) < 0:
            violations.append("mileage cannot be negative")
        for penalty in self.penalties:
            if int(penalty.get("amount", 0)) < 0:
                violations.append("penalty amount cannot be negative")
        for payment in self.payments:
            if int(payment.get("amount", 0)) < 0:
                violations.append("payment amount cannot be negative")
        if self.rental["state"] in ("active", "overdue"):
            if int(self.rental["dueAt"]) <= int(self.rental["startedAt"]):
                violations.append("rental dueAt must be after startedAt")
        if self.scooter["state"] == "rented" and int(self.customer["deposit"]) < 0:
            violations.append("deposit invariant")
        return violations

    def snapshot(self) -> dict:
        return {
            "now": self.now,
            "records": copy.deepcopy(self.records),
            "penalties": copy.deepcopy(self.penalties),
            "payments": copy.deepcopy(self.payments),
            "claims": copy.deepcopy(self.claims),
            "maintenance": copy.deepcopy(self.maintenance),
            "blacklist": copy.deepcopy(self.blacklist),
            "transitions": list(self.transitions),
            "last_error": self.last_error,
        }

    # --------------------------------------------------------- rule execution
    def apply_rule(self, rule_name: str) -> dict:
        """Evaluate a DSL rule against this world and return its assignments."""
        if self.program is None:
            return {}
        from ..core.interpreter import evaluate_rule
        return evaluate_rule(self.program, rule_name, self.world())
