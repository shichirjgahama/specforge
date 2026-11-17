# Проверка требований и тесты

Все проверки запускаются командой:

```text
python -m pytest -q
```

Текущий результат: 59 passed. Тесты не используют сеть и не требуют
административных прав. UI проверяется отдельным smoke-тестом (см.
раздел 4).

## 1. Соответствие пунктам 8.1 - 8.9

### 8.1 Ручной парсер с восстановлением

- Лексер и рекурсивный спуск: `core/lexer.py`, `core/parser.py`.
- Запрещенные библиотеки не используются: в `requirements.txt` нет lark,
  ply, pyparsing, antlr4, textx.
- Файл `specs/broken5.sforge` содержит 5 независимых ошибок.
- `test_parser_collects_exactly_five_errors` проверяет ровно 5 диагностик.
- `test_parser_recovers_and_keeps_later_declarations` проверяет, что после
  ошибочного объявления разбор продолжается и находит сущность и машину.
- `test_lexer_reports_position_of_unexpected_character` проверяет позицию
  `file:line:col`.

### 8.2 Семантический анализатор

- `core/semantic.py`: таблицы типов, проверка полей, Bool-условий,
  сигнатур операций, циклов правил, дубликатов.
- `specs/semantic3.sforge` содержит 3 семантические ошибки.
- `test_semantic_checker_returns_three_errors` получает 3 диагностики до
  запуска интерпретатора.
- `test_semantic_reports_unreachable_state` проверяет `W001`.

### 8.3 Доказуемо минимальный impact analysis

- `core/impact.py`: граф зависимостей, обратное замыкание, выбор тестов,
  `verify_minimality`.
- `test_threshold_change_impact_is_minimal` параметризован тремя CR и
  сравнивает множества упавших тестов для выбранного и полного прогона.
- `test_requirement_text_only_change_touches_linked_tests` проверяет, что
  текстовое изменение не ломает поведение.
- `test_unchanged_spec_has_empty_impact` проверяет пустой план для CR без
  изменений.
- Результаты: CR-001 (4 падения), CR-002 (6), CR-003 (1), во всех случаях
  `subset_failed == full_failed`.

### 8.4 Hypothesis и три кастомные стратегии

- `core/strategies.py`:
  - `st_dsl_program()` генерирует валидные программы с согласованными
    ссылками;
  - `st_invalid_transition()` генерирует переходы в несуществующие
    состояния;
  - `st_cr()` генерирует CR, меняющие 1-3 узла спецификации.
- `tests/test_hypothesis.py`:
  - каждая сгенерированная программа проходит парсер и семантику;
  - каждый недопустимый переход ловится как `E106` или `E117`;
  - после каждого CR все 8 свойств остаются истинными.
- Настройки: `max_examples=12`, `deadline=None`, фиксированный профиль
  Hypothesis для воспроизводимости.

### 8.5 Инкрементальный пересчет

- `core/incremental.py`: хеши узлов, версии требований, транзитивное
  замыкание, сравнение с полным пересчетом.
- `test_incremental_recompute_is_bounded_and_exact`: 8 из 174 узлов,
  4.6%, результат равен полному пересчету.
- `test_incremental_matches_full_analysis_for_other_requirement` проверяет
  R-001.
- `test_incremental_detects_spec_hash_change` проверяет изменение правила.

### 8.6 Детерминизм

- `test_runner_is_bit_for_bit_deterministic`: два прогона дают одинаковый
  digest и одинаковый JSON отчета.
- Порядок тестов и результатов сортируется по ID.
- Seed хранится в тесте и в прогоне.
- В digest не входят длительности.

### 8.7 Производительность

- `tests/test_performance.py`: парсинг 1000 строк < 100 мс, impact < 1 с,
  полный прогон < 10 с.
- `bench/profile_specforge.py`: до/после для двух оптимизаций,
  `bench/results.json`, `bench/profile.txt`.
- Подробности: `docs/performance.md`.

### 8.8 Миграции SQLite без alembic

- `storage/migrations.py`: таблица `schema_version`, три функции миграции.
- `test_migrations_upgrade_v1_to_v3_and_keep_data`: создать v1, вставить
  требование и версию спецификации, мигрировать до v3, проверить данные и
  таблицы.
- `test_migrate_is_idempotent`: повторная миграция не ломает базу.

### 8.9 Визуализация state machine

- `core/state_machine.py`: BFS достижимости, Тарьян для циклов, слоистая
  раскладка, SVG-рендер без networkx.
- `test_state_machine_layout_and_cycles`: проверяет циклы, координаты
  внутри холста, SVG.
- `test_state_machine_marks_unreachable_states`: состояние без входящих
  ребер помечается `unreachable`.
- UI рисует граф на Canvas: красный - недостижимое, оранжевый - цикл.

## 2. Файлы тестов

| Файл | Что проверяет |
|------|----------------|
| `tests/test_language.py` | лексер, парсер, восстановление, семантика, валидатор, граф |
| `tests/test_runtime.py` | сценарии, 60 тестов, детерминизм, 8 свойств, TTL, права |
| `tests/test_traceability_impact.py` | матрица, CR, минимальность, история, версии |
| `tests/test_incremental_storage.py` | инкрементальный кеш, миграции, репозиторий, кеш узлов |
| `tests/test_hypothesis.py` | три стратегии и свойства после CR |
| `tests/test_performance.py` | три лимита производительности |
| `tests/test_ui_cli.py` | CLI интеграция и smoke-проверка всех экранов UI |

## 3. Что именно доказывают ключевые тесты

- 5 ошибок парсера -> 5 диагностик, а не одна. Это проверка recovery.
- 3 семантические ошибки -> 3 диагностики до интерпретатора.
- Выбранные impact analysis тесты дают ровно то же множество падений, что
  и полный набор, для трех разных CR.
- 60 тестов делятся ровно на 20 сценарных, 20 пограничных и 20
  property-сгенерированных.
- Все 60 тестов зеленые на исходной спецификации.
- Два прогона совпадают побайтово по каноническому JSON.
- Миграция v1 -> v3 сохраняет строки.
- Инкрементальный пересчет не превышает 5% и совпадает с полным.

## 4. Ручная проверка UI

```text
python run.py
```

Экраны: Requirements, DSL, State machine, Traceability, Change requests,
Tests. Smoke-проверка без mainloop входит в `tests/test_ui_cli.py`:

```text
python -c "from specforge.services import SpecForgeService; from specforge.ui.app import SpecForgeApp; app=SpecForgeApp(SpecForgeService()); app.update(); print(list(app.screens)); app.destroy()"
```

## 5. Известные ограничения тестов

- Hypothesis использует ограниченное число примеров, чтобы прогон в
  аудитории занимал секунды. Увеличение `max_examples` не меняет логику.
- Property-проверки работают на конечном наборе seed (0..11), а не
  доказывают свойства для всех возможных последовательностей.
- UI не тестируется в headless CI: для него нужен дисплей Windows.
- Лимиты производительности измеряются на текущей машине и имеют запас.
