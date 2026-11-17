# CR-002: Raise the minimum rental battery to 25 percent

- Тип: `rule_threshold`
- Описание: Winter failures show that 20 percent is not enough to reach a station. The minimum battery becomes 25 percent for reservation and rental start.
- Версия спецификации до: `31d1953db2ef7190`
- Версия спецификации после: `9f31e7cb5ee7014e`
- Узлов изменено: 7
- Узлов затронуто: 15
- Тестов выбрано: 56 из 60

## Измененные узлы

- `const:minBattery`
- `entity:Scooter`
- `invariant:INV-02`
- `rule:BRI-01`
- `scenario:BatteryBoundary`
- `transition:ScooterState:available:reserve`
- `transition:ScooterState:reserved:rent`

## План прогона

- `T-001`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-002`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve
- `T-003`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve
- `T-005`: spec nodes: rule:BRI-01; requirements: R-005
- `T-006`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve; requirements: R-005
- `T-007`: spec nodes: rule:BRI-01
- `T-008`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve
- `T-009`: spec nodes: rule:BRI-01
- `T-010`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve
- `T-011`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-012`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-013`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-014`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-015`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-016`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-017`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-018`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-019`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-020`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-021`: spec nodes: rule:BRI-01; requirements: R-005
- `T-022`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve; requirements: R-005
- `T-023`: spec nodes: rule:BRI-01
- `T-024`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve
- `T-025`: spec nodes: rule:BRI-01
- `T-026`: spec nodes: rule:BRI-01
- `T-027`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve
- `T-028`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-029`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-030`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-031`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-032`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve
- `T-033`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-034`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-037`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-038`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent; requirements: R-005
- `T-039`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-041`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-042`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-043`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-044`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve; requirements: R-005
- `T-045`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-046`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-047`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-048`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve; requirements: R-005
- `T-049`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-050`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-051`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-052`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve; requirements: R-005
- `T-053`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-054`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-055`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-056`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve; requirements: R-005
- `T-057`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-058`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-059`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve, transition:ScooterState:reserved:rent
- `T-060`: spec nodes: rule:BRI-01, transition:ScooterState:available:reserve; requirements: R-005

## Результат до и после

- До изменения: 60 из 60 тестов проходили (базовая спецификация).
- После изменения: упавших тестов 6: T-006, T-022, T-042, T-046, T-047, T-055
- Прогон только выбранных тестов упал на: T-006, T-022, T-042, T-046, T-047, T-055
- Полный прогон упал на: T-006, T-022, T-042, T-046, T-047, T-055
- Минимальность (множества совпадают): True
- Тестов к перегенерации: 56
- Конфликты: нет

## Изменения требований

- `R-005`: criteria_add=['CR-002: battery 24 percent is rejected.', 'CR-002: battery 25 percent is accepted.'], notes=Minimum battery raised by CR-002.
