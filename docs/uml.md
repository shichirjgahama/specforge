# UML: компоненты и модель домена

Ниже две обязательные диаграммы. Те же диаграммы лежат в PlantUML формате:
`docs/diagrams/components.puml` и `docs/diagrams/domain.puml`.

## 1. Диаграмма компонентов

```mermaid
flowchart TB
    subgraph Presentation
        UI["UI (tkinter)<br/>6 экранов"]
        CLI["CLI (argparse)"]
    end

    subgraph Application
        SVC["SpecForgeService<br/>координатор состояния"]
        REP["HTML report<br/>render_html_report"]
    end

    subgraph Language["Язык и анализ"]
        LEX["Lexer"]
        PAR["Parser + recovery"]
        SEM["Semantic analyzer"]
        VAL["Validator"]
        NODES["SpecIndex<br/>хеши и граф зависимостей"]
        INT["Interpreter"]
        PROPS["8 properties"]
    end

    subgraph Runtime
        ENG["Simulation<br/>доменный движок"]
        GEN["Test generator<br/>60 тестов"]
        RUN["Deterministic runner"]
        IMP["Impact analysis"]
        INC["Incremental cache"]
    end

    subgraph Storage
        REPO["Repository"]
        MIG["Migrations v1 -> v3"]
        DB[("SQLite<br/>профиль пользователя")]
    end

    UI --> SVC
    CLI --> SVC
    SVC --> LEX
    LEX --> PAR
    PAR --> SEM
    SEM --> VAL
    SEM --> NODES
    NODES --> IMP
    NODES --> INC
    SVC --> INT
    SVC --> PROPS
    SVC --> ENG
    SVC --> GEN
    GEN --> RUN
    RUN --> ENG
    SVC --> IMP
    IMP --> RUN
    SVC --> REP
    SVC --> REPO
    REPO --> MIG
    REPO --> DB
```

Поток данных: исходник DSL проходит лексер, парсер, семантику и
валидатор; `SpecIndex` присваивает узлам хеши и строит зависимости. Движок
и интерпретатор исполняют модель, генератор создает тесты, runner
фиксирует результаты. `SpecForgeService` связывает это с UI, CLI, SQLite и
отчетом.

## 2. Диаграмма модели домена

```mermaid
classDiagram
    class Customer {
        +String id
        +String status
        +Money deposit
        +Money debt
        +Int lateReturns
        +Time blockedUntil
    }
    class Scooter {
        +String id
        +ScooterState state
        +Int battery
        +Int mileageSinceService
        +Time reservedUntil
    }
    class Station {
        +String id
        +String name
        +Int capacity
    }
    class Reservation {
        +String id
        +ReservationState state
        +Time createdAt
        +Time expiresAt
    }
    class Rental {
        +String id
        +RentalState state
        +Time startedAt
        +Time dueAt
        +Time returnedAt
        +Int minutesLate
        +Money lateFee
        +Bool closed
    }
    class Tariff {
        +Money perMinute
        +Money depositAmount
        +Money lateFeePerHour
        +Int graceMinutes
        +Int maxHours
    }
    class Payment {
        +Money amount
        +String kind
        +String status
    }
    class Penalty {
        +Money amount
        +String reason
        +Bool paid
    }
    class DamageClaim {
        +Money amount
        +String state
    }
    class MaintenanceRecord {
        +String kind
        +Time startedAt
        +Int mileageAtService
    }
    class BlacklistEntry {
        +String reason
        +Time expiresAt
    }
    class Season {
        +Int coefficient
        +Int startMonth
        +Int endMonth
    }
    class Operator
    class Admin

    Customer "1" --> "0..*" Rental : создает
    Customer "1" --> "0..*" Reservation : бронирует
    Customer "1" --> "0..*" Penalty : получает
    Customer "1" --> "0..*" Payment : платит
    Customer "1" --> "0..*" BlacklistEntry : попадает
    Scooter "1" --> "0..*" Rental : арендуется
    Scooter "1" --> "0..*" Reservation : резервируется
    Scooter "1" --> "0..*" MaintenanceRecord : обслуживается
    Station "1" --> "0..*" Scooter : хранит
    Rental "1" --> "0..*" Penalty : порождает
    Rental "1" --> "0..*" Payment : оплачивает
    Rental "1" --> "0..1" DamageClaim : имеет
    Tariff "1" --> "0..*" Rental : тарифицирует
    Season "1" --> "0..*" Tariff : корректирует

    class ScooterState {
        <<enumeration>>
        available
        reserved
        rented
        maintenance
        lost
        retired
    }
    class RentalState {
        <<enumeration>>
        draft
        active
        overdue
        closed
        disputed
        cancelled
    }
    class ReservationState {
        <<enumeration>>
        none
        active
        used
        cancelled
        expired
    }
    Scooter --> ScooterState
    Rental --> RentalState
    Reservation --> ReservationState
```

## 3. Машины состояний

`ScooterState`:

```text
available -> reserved : reserve
reserved -> available : cancel
reserved -> available : expire
reserved -> rented : rent
rented -> available : return
rented -> maintenance : returnFault
rented -> lost : lost
maintenance -> available : service
maintenance -> retired : retire
lost -> maintenance : recover
```

`RentalState`:

```text
draft -> active : start / reopen
draft -> cancelled : cancel
active -> overdue : markOverdue
active -> closed : close
overdue -> closed : close
active -> disputed : dispute
overdue -> disputed : dispute
disputed -> closed : resolve
```

Графы строятся в `core/state_machine.py`: BFS для достижимости, Тарьян для
циклов, слоистая раскладка с barycenter-упорядочиванием. Внешние библиотеки
для layout не используются.
