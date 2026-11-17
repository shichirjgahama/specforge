# CR-004: Add a helmet deposit field to Rental

- Тип: `entity_structure`
- Описание: A separate helmet deposit is introduced in the data model. The change is structural: it must be propagated to all tests that touch the Rental entity, even though behaviour stays the same.
- Версия спецификации до: `31d1953db2ef7190`
- Версия спецификации после: `ccdfb6dfc071af1f`
- Узлов изменено: 6
- Узлов затронуто: 39
- Тестов выбрано: 60 из 60

## Измененные узлы

- `entity:Rental`
- `field:Rental.helmetDeposit`
- `field:Rental.tariffId`
- `scenario:HappyPath`
- `transition:RentalState:active:close`
- `transition:ScooterState:rented:return`

## План прогона

- `T-001`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close; requirements: R-003
- `T-002`: spec nodes: invariant:INV-06, invariant:INV-08, transition:RentalState:draft:cancel
- `T-003`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-03
- `T-004`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-12
- `T-005`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-006`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-007`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-008`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-009`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-010`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-011`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-12, transition:RentalState:draft:start
- `T-012`: spec nodes: field:Rental.lateFee, field:Rental.minutesLate, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-013`: spec nodes: field:Rental.lateFee, field:Rental.minutesLate, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-014`: spec nodes: field:Rental.lateFee, field:Rental.minutesLate, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-015`: spec nodes: field:Rental.lateFee, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-016`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:closed:reopen, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-017`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-018`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-08, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-019`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-08, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-020`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-021`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-022`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-023`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-024`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-025`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-026`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-027`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-028`: spec nodes: field:Rental.lateFee, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-029`: spec nodes: field:Rental.lateFee, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-030`: spec nodes: field:Rental.lateFee, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-031`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-12, transition:RentalState:draft:start
- `T-032`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-03
- `T-033`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-08, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-034`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-08, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-035`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-10
- `T-036`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-10
- `T-037`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-09, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-038`: spec nodes: field:Rental.batteryUsed, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close; requirements: R-003
- `T-039`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:closed:reopen, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-040`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-05
- `T-041`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close; requirements: R-003
- `T-042`: spec nodes: field:Rental.lateFee, field:Rental.minutesLate, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-043`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-044`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-045`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close; requirements: R-003
- `T-046`: spec nodes: field:Rental.lateFee, field:Rental.minutesLate, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-047`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-048`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-049`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close; requirements: R-003
- `T-050`: spec nodes: field:Rental.lateFee, field:Rental.minutesLate, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-051`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-052`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-053`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close; requirements: R-003
- `T-054`: spec nodes: field:Rental.lateFee, field:Rental.minutesLate, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-055`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-056`: spec nodes: invariant:INV-06, invariant:INV-08
- `T-057`: spec nodes: field:Rental.state, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close; requirements: R-003
- `T-058`: spec nodes: field:Rental.lateFee, field:Rental.minutesLate, invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-05, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:active:markOverdue, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-059`: spec nodes: invariant:INV-06, invariant:INV-08, rule:BRI-03, rule:BRI-04, rule:BRI-12, transition:RentalState:active:close, transition:RentalState:draft:start, transition:RentalState:overdue:close
- `T-060`: spec nodes: invariant:INV-06, invariant:INV-08

## Результат до и после

- До изменения: 60 из 60 тестов проходили (базовая спецификация).
- После изменения: упавших тестов 0: нет
- Прогон только выбранных тестов упал на: нет
- Полный прогон упал на: нет
- Минимальность (множества совпадают): True
- Тестов к перегенерации: 60
- Конфликты: нет

## Изменения требований

- `R-003`: criteria_add=['CR-004: the rental record stores the helmet deposit separately.']
