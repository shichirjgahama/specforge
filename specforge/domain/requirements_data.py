"""Twenty requirements for the RollCity scooter sharing domain."""

REQUIREMENTS = [
    {
        "id": "R-001",
        "title": "Reserve an available scooter",
        "story": "As a customer I want to reserve an available scooter so that it is "
                 "waiting for me at the station for a short time.",
        "criteria": [
            "A reservation is created only for a scooter in state available.",
            "The reservation expires 15 minutes after creation.",
            "While reserved the scooter cannot be reserved by another customer.",
        ],
        "kind": "functional",
        "role": "Customer",
    },
    {
        "id": "R-002",
        "title": "Start a rental from a reservation",
        "story": "As a customer I want to start a rental from my active reservation so "
                 "that I can ride within the reservation window.",
        "criteria": [
            "The rental starts only when the reservation is active and not expired.",
            "The scooter moves from reserved to rented.",
            "A rental deadline is set 24 hours after the start.",
        ],
        "kind": "functional",
        "role": "Customer",
    },
    {
        "id": "R-003",
        "title": "Return a scooter and close the rental",
        "story": "As a customer I want to return a scooter at any station so that the "
                 "rental is closed and the scooter becomes available again.",
        "criteria": [
            "Return closes the rental and records the return time.",
            "A serviceable scooter returns to state available.",
            "Battery and mileage are updated after the return.",
        ],
        "kind": "functional",
        "role": "Customer",
    },
    {
        "id": "R-004",
        "title": "Deposit is required before the first rental",
        "story": "As a service owner I want a deposit of 3000 rubles before a rental so "
                 "that damage and lost scooters are covered.",
        "criteria": [
            "Reservation is rejected when the deposit is below 3000.",
            "A deposit of exactly 3000 is accepted.",
            "The deposit is a non negative amount at all times.",
        ],
        "kind": "functional",
        "role": "Customer",
    },
    {
        "id": "R-005",
        "title": "Reject a scooter with a low battery",
        "story": "As a customer I must not receive a scooter with less than 20 percent "
                 "battery so that I do not get stranded.",
        "criteria": [
            "Battery 19 percent is rejected with E_BATTERY_LOW.",
            "Battery exactly 20 percent is accepted.",
            "The rejection leaves the scooter in its previous state.",
        ],
        "kind": "exception",
        "role": "Customer",
    },
    {
        "id": "R-006",
        "title": "Reject a scooter that needs maintenance",
        "story": "As an operator I want scooters with 500 km since the last service to "
                 "leave the fleet so that safety is not compromised.",
        "criteria": [
            "Mileage 499 km is still rentable.",
            "Mileage 500 km or more is rejected with E_MAINTENANCE_DUE.",
            "After a return that crosses 500 km the scooter goes to maintenance.",
        ],
        "kind": "exception",
        "role": "Operator",
    },
    {
        "id": "R-007",
        "title": "Charge a late return fee",
        "story": "As a service owner I want a fee of 500 rubles per started hour after a "
                 "10 minute grace period so that late returns are discouraged.",
        "criteria": [
            "A return within 10 minutes after the deadline costs nothing.",
            "11 minutes late costs 500 rubles, 70 minutes late costs 500 rubles.",
            "130 minutes late costs 1000 rubles because the second hour has started.",
        ],
        "kind": "functional",
        "role": "Customer",
    },
    {
        "id": "R-008",
        "title": "Block an extremely overdue customer",
        "story": "As a service owner I want a customer who is more than 24 hours late to "
                 "be blocked for 7 days so that abandoned rentals are prevented.",
        "criteria": [
            "A rental returned 25 hours late blocks the customer.",
            "The block lasts 7 days from the return.",
            "A blocked customer cannot create new rentals.",
        ],
        "kind": "exception",
        "role": "Operator",
    },
    {
        "id": "R-009",
        "title": "Blacklist after three late returns",
        "story": "As a service owner I want a customer with three late returns inside 30 "
                 "days to be blocked so that repeated violations have consequences.",
        "criteria": [
            "Two late returns in the window do not block the customer.",
            "The third late return inside 30 days blocks the account.",
            "Returns older than 30 days do not count toward the limit.",
        ],
        "kind": "exception",
        "role": "Operator",
    },
    {
        "id": "R-010",
        "title": "Charge for a lost scooter",
        "story": "As a service owner I want a lost scooter to cost 25000 rubles and block "
                 "the customer so that losses are compensated.",
        "criteria": [
            "A lost report is accepted only during an active rental.",
            "A penalty of 25000 rubles is created.",
            "The customer is blocked and the scooter is in state lost.",
        ],
        "kind": "exception",
        "role": "Customer",
    },
    {
        "id": "R-011",
        "title": "Damage claim window is 48 hours",
        "story": "As a customer I want to report damage within 48 hours after the return "
                 "so that late claims do not reopen old rentals.",
        "criteria": [
            "A claim exactly 48 hours after the return is accepted.",
            "A claim 48 hours and 1 minute after the return is rejected with E_CLAIM_LATE.",
            "A claim is possible only for a closed rental.",
        ],
        "kind": "boundary",
        "role": "Customer",
    },
    {
        "id": "R-012",
        "title": "Refund the deposit within three business days",
        "story": "As a customer I want my deposit refunded no later than three business "
                 "days after the rental is closed so that money is not held forever.",
        "criteria": [
            "A refund is blocked while a rental is active.",
            "A refund is blocked while penalties are unpaid.",
            "The refund deadline skips weekends.",
        ],
        "kind": "boundary",
        "role": "Customer",
    },
    {
        "id": "R-013",
        "title": "Seasonal price coefficient",
        "story": "As a service owner I want a 130 percent coefficient from May to "
                 "September so that high season demand is balanced.",
        "criteria": [
            "April 30 uses coefficient 100.",
            "May 1 uses coefficient 130.",
            "The coefficient applies to the rental price only.",
        ],
        "kind": "functional",
        "role": "Customer",
    },
    {
        "id": "R-014",
        "title": "Only one active rental per customer",
        "story": "As a service owner I want a customer to hold at most one active rental "
                 "so that scooters are not hoarded.",
        "criteria": [
            "A second reservation during an active rental is rejected.",
            "After the rental is closed a new reservation is possible.",
            "The rejection is reported as E_ACTIVE_RENTAL.",
        ],
        "kind": "boundary",
        "role": "Customer",
    },
    {
        "id": "R-015",
        "title": "Reservation expires after 15 minutes",
        "story": "As a service owner I want unused reservations to expire so that scooters "
                 "return to the pool quickly.",
        "criteria": [
            "A start exactly 15 minutes after reservation is accepted.",
            "A start 16 minutes after reservation fails with E_RESERVATION_EXPIRED.",
            "An expired reservation frees the scooter.",
        ],
        "kind": "boundary",
        "role": "Customer",
    },
    {
        "id": "R-016",
        "title": "Finish maintenance and return to service",
        "story": "As an operator I want to finish maintenance so that a serviced scooter "
                 "is available and its mileage counter is reset.",
        "criteria": [
            "Service is allowed only for a scooter in maintenance.",
            "Mileage resets to zero and battery to 100 percent.",
            "The scooter becomes available for the next customer.",
        ],
        "kind": "functional",
        "role": "Operator",
    },
    {
        "id": "R-017",
        "title": "Cancel a reservation",
        "story": "As a customer I want to cancel a reservation before it expires so that "
                 "the scooter is released immediately.",
        "criteria": [
            "Cancel moves the scooter from reserved to available.",
            "Cancel clears the reservation deadline.",
            "Cancel is not possible for a rented scooter.",
        ],
        "kind": "functional",
        "role": "Customer",
    },
    {
        "id": "R-018",
        "title": "Blocked customer cannot start a rental",
        "story": "As a service owner I want a blocked customer to be unable to reserve or "
                 "rent so that debt and violations are resolved first.",
        "criteria": [
            "A blocked customer receives E_CUSTOMER_BLOCKED.",
            "Reservation and rental start are both rejected.",
            "The scooter stays available.",
        ],
        "kind": "exception",
        "role": "Customer",
    },
    {
        "id": "R-019",
        "title": "Operator manages customer blocks",
        "story": "As an operator I want to block and unblock a customer manually so that "
                 "support cases can be resolved without developer help.",
        "criteria": [
            "Only Operator and Admin roles may block a customer.",
            "A customer cannot block another customer.",
            "Unblock returns the account to active.",
        ],
        "kind": "functional",
        "role": "Operator",
    },
    {
        "id": "R-020",
        "title": "Invalid operations never change state",
        "story": "As a developer I want an invalid operation to return a domain error and "
                 "leave the world unchanged so that failed requests are safe to retry.",
        "criteria": [
            "A rental start without a reservation returns E_NO_RESERVATION.",
            "An unknown operation returns E_UNKNOWN_OP.",
            "A rejected operation does not create penalties or payments.",
        ],
        "kind": "exception",
        "role": "Customer",
    },
]
