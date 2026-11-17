# CR-003: Shorten the damage claim window to 24 hours

- Тип: `rule_threshold`
- Описание: The insurer accepts claims only within one day. The claim window changes from 48 to 24 hours and requirement R-011 is updated.
- Версия спецификации до: `31d1953db2ef7190`
- Версия спецификации после: `29ad8fe47a61adb1`
- Узлов изменено: 8
- Узлов затронуто: 8
- Тестов выбрано: 4 из 60

## Измененные узлы

- `const:damageClaimHours`
- `entity:DamageClaim`
- `entity:Rental`
- `entity:Scooter`
- `rule:BRI-08`
- `scenario:ClaimWindow`
- `transition:RentalState:active:dispute`
- `transition:RentalState:overdue:dispute`

## План прогона

- `T-018`: spec nodes: rule:BRI-08; requirements: R-011
- `T-019`: spec nodes: rule:BRI-08; requirements: R-011
- `T-033`: spec nodes: rule:BRI-08; requirements: R-011
- `T-034`: spec nodes: rule:BRI-08; requirements: R-011

## Результат до и после

- До изменения: 60 из 60 тестов проходили (базовая спецификация).
- После изменения: упавших тестов 1: T-033
- Прогон только выбранных тестов упал на: T-033
- Полный прогон упал на: T-033
- Минимальность (множества совпадают): True
- Тестов к перегенерации: 4
- Конфликты: нет

## Изменения требований

- `R-011`: criteria_add=['CR-003: a claim 24 hours and 1 minute after return is rejected.'], notes=Claim window reduced by CR-003.
