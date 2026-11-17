# CR-005: Clarify the return wording without changing behaviour

- Тип: `requirement_text`
- Описание: Editorial change: requirement R-003 explains that the rental closes immediately after the return. No rule changes, tests must stay green.
- Версия спецификации до: `31d1953db2ef7190`
- Версия спецификации после: `31d1953db2ef7190`
- Узлов изменено: 4
- Узлов затронуто: 4
- Тестов выбрано: 7 из 60

## Измененные узлы

- `entity:Rental`
- `scenario:HappyPath`
- `transition:RentalState:active:close`
- `transition:ScooterState:rented:return`

## План прогона

- `T-001`: requirements: R-003
- `T-038`: requirements: R-003
- `T-041`: requirements: R-003
- `T-045`: requirements: R-003
- `T-049`: requirements: R-003
- `T-053`: requirements: R-003
- `T-057`: requirements: R-003

## Результат до и после

- До изменения: 60 из 60 тестов проходили (базовая спецификация).
- После изменения: упавших тестов 0: нет
- Прогон только выбранных тестов упал на: нет
- Полный прогон упал на: нет
- Минимальность (множества совпадают): True
- Тестов к перегенерации: 0
- Конфликты: нет

## Изменения требований

- `R-003`: criteria_add=['CR-005: the rental closes immediately after the return event.'], story=As a customer I want to return a scooter at any station so that the rental closes immediately and the scooter becomes available for the next customer.
