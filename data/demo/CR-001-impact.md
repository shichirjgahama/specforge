# CR-001: Shorten the late fee grace period to 5 minutes

- Тип: `rule_threshold`
- Описание: Support reports that customers exploit the 10 minute grace period. The grace period becomes 5 minutes, the hourly fee stays 500. Requirement R-007 is updated with the new threshold.
- Версия спецификации до: `31d1953db2ef7190`
- Версия спецификации после: `f1b4716dad00c8bc`
- Узлов изменено: 12
- Узлов затронуто: 12
- Тестов выбрано: 33 из 60

## Измененные узлы

- `const:graceMinutes`
- `entity:Penalty`
- `entity:Rental`
- `entity:Tariff`
- `invariant:INV-03`
- `invariant:INV-04`
- `invariant:INV-06`
- `invariant:INV-08`
- `rule:BRI-04`
- `scenario:LateFeeCalculation`
- `transition:RentalState:active:markOverdue`
- `transition:RentalState:overdue:close`

## План прогона

- `T-001`: spec nodes: rule:BRI-04
- `T-012`: spec nodes: rule:BRI-04; requirements: R-007
- `T-013`: spec nodes: rule:BRI-04; requirements: R-007
- `T-014`: spec nodes: rule:BRI-04; requirements: R-007
- `T-015`: spec nodes: rule:BRI-04
- `T-016`: spec nodes: rule:BRI-04
- `T-017`: spec nodes: rule:BRI-04
- `T-018`: spec nodes: rule:BRI-04
- `T-019`: spec nodes: rule:BRI-04
- `T-020`: spec nodes: rule:BRI-04
- `T-028`: spec nodes: rule:BRI-04; requirements: R-007
- `T-029`: spec nodes: rule:BRI-04; requirements: R-007
- `T-030`: spec nodes: rule:BRI-04; requirements: R-007
- `T-033`: spec nodes: rule:BRI-04
- `T-034`: spec nodes: rule:BRI-04
- `T-037`: spec nodes: rule:BRI-04
- `T-038`: spec nodes: rule:BRI-04
- `T-039`: spec nodes: rule:BRI-04
- `T-041`: spec nodes: rule:BRI-04
- `T-042`: spec nodes: rule:BRI-04; requirements: R-007
- `T-043`: spec nodes: rule:BRI-04
- `T-045`: spec nodes: rule:BRI-04
- `T-046`: spec nodes: rule:BRI-04; requirements: R-007
- `T-047`: spec nodes: rule:BRI-04
- `T-049`: spec nodes: rule:BRI-04
- `T-050`: spec nodes: rule:BRI-04; requirements: R-007
- `T-051`: spec nodes: rule:BRI-04
- `T-053`: spec nodes: rule:BRI-04
- `T-054`: spec nodes: rule:BRI-04; requirements: R-007
- `T-055`: spec nodes: rule:BRI-04
- `T-057`: spec nodes: rule:BRI-04
- `T-058`: spec nodes: rule:BRI-04; requirements: R-007
- `T-059`: spec nodes: rule:BRI-04

## Результат до и после

- До изменения: 60 из 60 тестов проходили (базовая спецификация).
- После изменения: упавших тестов 4: T-012, T-013, T-028, T-030
- Прогон только выбранных тестов упал на: T-012, T-013, T-028, T-030
- Полный прогон упал на: T-012, T-013, T-028, T-030
- Минимальность (множества совпадают): True
- Тестов к перегенерации: 33
- Конфликты: нет

## Изменения требований

- `R-007`: criteria_add=['CR-001: the grace period is 5 minutes starting from version 2.', 'CR-001: 6 minutes late costs 500 rubles.'], notes=Grace period reduced by CR-001.
