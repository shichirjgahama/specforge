# DSL SpecForge: грамматика, семантика, диагностика

Файлы спецификаций имеют расширение `.sforge` (пример:
`specs/scooter_share.sforge`). Язык собственный: это не YAML и не JSON,
конструкции и семантика описаны ниже. Парсер написан вручную: лексер и
рекурсивный спуск, без lark, ply, pyparsing, antlr4, textx.

## 1. Пример

```text
spec RollCity version 3;

const lateFeePerHour: Money = 500;
const graceMinutes: Int = 10;

enum ScooterState { available, reserved, rented, maintenance, lost, retired }

entity Scooter {
  id: Identifier;
  state: State<ScooterState> = available;
  battery: Int [0..100] = 100;
  mileageSinceService: Int >= 0 = 0;
}

role Customer {
  may reserve, rent, return, pay;
  forbid service, grant;
}

state ScooterState {
  initial available;
  available -> reserved : reserve
    when scooter.battery >= 20 do {
      scooter.state := reserved;
    };
  link R-001, R-005;
  reserved -> rented : rent when scooter.battery >= 20 do {
    scooter.state := rented;
  };
  link R-002;
}

rule BRI-04 priority 80 {
  when rental.minutesLate > graceMinutes
  then {
    rental.lateFee := lateFeePerHour *
      ((rental.minutesLate - graceMinutes + 59) / 60);
  } else {
    rental.lateFee := 0;
  }
  ensures rental.lateFee >= 0;
}
link R-007;

invariant INV-01 always customer.deposit >= 0
  message "deposit can never become negative";
link R-004, R-012;

scenario HappyPath {
  given customer.deposit = 3000;
  given scooter.battery = 90;
  step reserve(customer, scooter);
  step start_rental(customer, scooter);
  step advance(55);
  step return_scooter(customer, scooter);
  expect rental.state == closed;
  expect lastError() == "";
}
link R-001, R-002, R-003;
```

## 2. Лексика

- Комментарии: `// ...`, `# ...`, `/* ... */`.
- Идентификаторы: `[A-Za-z_][A-Za-z0-9_]*`.
- Идентификаторы требований и правил: `R-001`, `BRI-04`, `INV-01`,
  `CR-002`, `T-060` распознаются одним токеном (заглавный префикс, дефис,
  цифры).
- Целые числа: `[0-9]+`. Дробных чисел нет: деньги в рублях, время в
  минутах.
- Строки: `"..."` с экранированием `\"`, `\\`, `\n`, `\t`.
- Символы: `->`, `:=`, `==`, `!=`, `<=`, `>=`, `&&`, `||`, `..`,
  `{ } ( ) [ ] ; : , . < > + - * / % = ! ?`.

Позиции: строка и столбец считаются с 1, как в редакторах. Диагностика
печатается в формате `file:line:col: severity CODE: message (hint: ...)`.

## 3. Грамматика (EBNF)

```ebnf
program        = header { declaration } EOF ;
header         = "spec" IDENT "version" NUMBER ";" ;

declaration    = constDecl | entityDecl | enumDecl | roleDecl | stateDecl
               | ruleDecl | invariantDecl | scenarioDecl | linkStmt ;

constDecl      = "const" IDENT ":" type "=" expr ";" ;
entityDecl     = "entity" IDENT "{" { field } "}" [ ";" ] ;
field          = IDENT ":" type { constraint } [ "=" expr ] ";" ;
constraint     = "[" NUMBER ".." NUMBER "]"
               | "in" "{" IDENT { "," IDENT } "}"
               | (">=" | ">" | "<=" | "<") NUMBER ;
type           = IDENT [ "<" IDENT ">" ] [ "?" ] ;

enumDecl       = "enum" IDENT "{" IDENT { "," IDENT } "}" [ ";" ] ;
roleDecl       = "role" IDENT "{" { ( "may" | "forbid" ) identList ";" } "}"
                 [ ";" ] ;
identList      = IDENT { "," IDENT } ;

stateDecl      = "state" IDENT "{" { "initial" IDENT ";"
                                     | edge | linkStmt } "}" [ ";" ] ;
edge           = IDENT "->" IDENT ":" IDENT [ "when" expr ]
                 [ "do" ( block | stmt ) ] ";" ;

ruleDecl       = "rule" IDENT [ "priority" NUMBER [ ";" ] ] "{"
                 [ "priority" NUMBER [ ";" ] ]
                 "when" expr "then" stmtList [ "else" stmtList ]
                 [ "ensures" expr ";" ] "}" [ ";" ] ;
stmtList       = block | { stmt } ;
block          = "{" { stmt } "}" ;
stmt           = "apply" IDENT ";"
               | "assert" expr ";"
               | "emit" STRING ";"
               | path ( ":=" | "=" ) expr ";" ;
path           = IDENT { "." IDENT } ;

invariantDecl  = "invariant" IDENT "always" expr
                 [ "message" STRING ] ";" ;
scenarioDecl   = "scenario" IDENT "{"
                 { given | step | expect } "}" [ ";" ] ;
given          = "given" path ( "=" | ":=" ) expr ";" ;
step           = "step" IDENT "(" [ expr { "," expr } ] ")" ";" ;
expect         = "expect" expr ";" ;

linkStmt       = "link" (REF | IDENT | STRING)
                 { "," (REF | IDENT | STRING) } ";" ;

expr           = orExpr ;
orExpr         = andExpr { ( "or" | "||" ) andExpr } ;
andExpr        = notExpr { ( "and" | "&&" ) notExpr } ;
notExpr        = ( "not" | "!" ) notExpr | comparison ;
comparison     = additive { ( "==" | "!=" | "<" | "<=" | ">" | ">=" )
                            additive | "in" inSet } ;
inSet          = "{" [ expr { "," expr } ] "}"
               | "[" [ expr { "," expr } ] "]"
               | additive ;
additive       = multiplicative { ( "+" | "-" ) multiplicative } ;
multiplicative = unary { ( "*" | "/" | "%" ) unary } ;
unary          = ( "-" | "+" ) unary | postfix ;
postfix        = primary { "." IDENT } ;
primary        = NUMBER | STRING | "true" | "false"
               | IDENT [ "(" [ expr { "," expr } ] ")" ]
               | "(" expr ")" ;
```

`link` после объявления прикрепляет требование к предыдущему узлу. Внутри
`state` после перехода `link` прикрепляет требование именно к переходу.
Это создает ребра трассируемости.

## 4. Семантика конструкций

### 4.1 `spec` и `const`

`spec Name version N;` задает имя и версию спецификации. Версия участвует в
отчете, но не влияет на поведение. `const` объявляет типизированную
константу, доступную в выражениях и используемую движком как конфигурация
(`CONFIG_MAP` в `runtime/engine.py`). Имена констант фиксированы для
параметров движка: `lateFeePerHour`, `graceMinutes`, `depositAmount`,
`maxRentalHours`, `perMinutePrice`, `minBattery`, `serviceMileage`,
`reservationTtlMinutes`, `damageClaimHours`, `refundBusinessDays`,
`blacklistLateReturns`, `blacklistWindowDays`, `seasonCoefficient`,
`seasonStartMonth`, `seasonEndMonth`, `lostFee`, `overdueBlockHours`,
`blockDays`. Остальные константы разрешены, но движок их не читает.

### 4.2 `entity` и `field`

Поле имеет тип, необязательные ограничения и значение по умолчанию.
Ограничения:

- `[low..high]` - целочисленный диапазон;
- `in {a, b, c}` - допустимое множество значений;
- `>= n`, `> n`, `<= n`, `< n` - односторонняя граница.

Ограничения проверяются статически для литеральных присваиваний
(`E132`) и участвуют в генерации тестов. Тип `State<E>` ссылается на enum
`E` и хранит имя состояния. Тип `Entity` (имя сущности) допустим для ссылок
на другие сущности. `?` означает необязательность на уровне модели.

### 4.3 `enum`

Перечисление состояний или категорий. Имена членов должны быть уникальны
внутри enum. Совпадение имен между enum допустимо, но при безусловном
использовании выдается предупреждение `W003`; контекст `State<E>` снимает
неоднозначность.

### 4.4 `role`

Список разрешенных (`may`) и запрещенных (`forbid`) прав. Право - это имя
из каталога операций (`core/ops.py`). Пересечение `may` и `forbid`
запрещено (`E123`). Движок строит карту роль -> множество прав и проверяет
ее перед каждой операцией. Роль берется из записи актора, а не из глобальной
переменной, поэтому подмена актора не дает прав.

### 4.5 `state`

Имя машины должно совпадать с именем enum (`E106`). `initial` задает
начальное состояние. Переход `A -> B : event when guard do { actions };`
означает:

1. переход возможен, только если текущее состояние равно `A`;
2. guard должен быть Bool и вычисляться в true;
3. действия выполняются последовательно и меняют поля модели;
4. после перехода состояние равно `B`.

Событие уникально в пределах исходного состояния (`E117`); один и тот же
event из разных состояний допустим (например, `close` из `active` и из
`overdue`). Недостижимые состояния дают `W001` и подсвечиваются красным в
графе; циклы находятся через алгоритм Тарьяна и подсвечиваются оранжевым.

### 4.6 `rule`

Правило вида "если - то - иначе" с постусловием:

```text
rule Name priority 10 {
  when <Bool>
  then { <statements> }
  else { <statements> }
  ensures <Bool>;
}
```

`priority` влияет на порядок применения при конфликте. `apply Other;`
вызывает другое правило; циклы вызовов запрещены (`E118`). `assert`
проверяет условие во время исполнения, `emit` пишет сообщение в трассу.
`ensures` проверяется интерпретатором после выполнения ветки; нарушение
дает ошибку исполнения. Валидатор сообщает о двух правилах, которые пишут
одно поле при одинаковом условии и приоритете (`E131`), и о литеральных
присваиваниях вне ограничений (`E132`).

### 4.7 `invariant`

`invariant Name always <Bool> message "..."`; проверяется интерпретатором
после каждого шага сценария, каждым тестом и в property-проверках. Это не
assert внутри правила, а глобальное свойство модели.

### 4.8 `scenario`

Сценарий - исполняемая последовательность:

- `given path = expr;` задает поле мира или виртуальное время `now`;
- `step op(args);` вызывает операцию движка;
- `expect expr;` проверяет утверждение после шагов.

Доступные операции: `reserve`, `start_rental`, `cancel_reservation`,
`return_scooter`, `report_lost`, `service_done`, `block_customer`,
`unblock_customer`, `claim_damage`, `refund_deposit`, `pay_penalty`,
`advance`, `expire_reservation`, `grant_role`. Аргументы типизированы:
клиент, самокат, оператор, аренда, целые минуты.

Сценарий исполняется `Interpreter.run_scenario`: после каждого шага
сверяются переходы с машиной состояний и проверяются инварианты. Ошибка
операции не прерывает сценарий: она доступна через `lastError()`, что
позволяет описывать негативные сценарии.

## 5. Система типов

| Тип | Значения | Совместимость |
|-----|----------|---------------|
| Int | целые | с Money в арифметике; с Time как минуты в литералах и сравнениях |
| Money | целые рубли | с Int |
| Text | строки | равенство и вхождение |
| Bool | true/false | условия |
| Time | минуты от 2026-01-01 | сравнение, `+ Int`, `- Int` |
| Identifier | строковый идентификатор | сравнение |
| State<E> | состояние enum E | сравнение с членом E |
| E | член перечисления | с State<E> |
| Entity | запись домена | доступ к полям |

Мир выражений: каждая сущность доступна по имени с маленькой буквы
(`Scooter` -> `scooter`, `MaintenanceRecord` -> `maintenanceRecord`),
`now` - текущее виртуальное время.

Встроенные функции:

| Функция | Результат |
|---------|-----------|
| min(a, b), max(a, b), abs(a) | число |
| minutesBetween(t1, t2), hoursBetween, daysBetween | Int |
| now() | Time |
| lastError() | Text, код последней ошибки |
| countPenalties(customer), totalPenalties(customer) | Int, Money |
| isBlocked(customer) | Bool |
| len(text), contains(text, part), startsWith(text, prefix) | Int, Bool |
| weekday(minutes) | Int, 0 = понедельник |
| formatTime(minutes) | Text |
| hasPermission(role, permission) | Bool |

## 6. Диагностика

Диагностика имеет код, серьезность, позицию, сообщение и подсказку.
Основные коды:

| Код | Категория | Смысл |
|-----|-----------|-------|
| E001 | лексер | незакрытая строка |
| E002 | лексер | недопустимый символ |
| E003 | лексер | незакрытый блочный комментарий |
| E010 | парсер | ожидался конкретный токен |
| E011 | парсер | ожидался идентификатор |
| E012 | парсер | неизвестное объявление |
| E013 | парсер | ожидалось выражение |
| E015 | парсер | пропущена точка с запятой |
| E016 | парсер | неверная версия |
| E017 | парсер | лишняя закрывающая скобка |
| E018 | парсер | неверная граница ограничения |
| E019 | парсер | неверное значение в множестве |
| E020 | парсер | член enum не идентификатор |
| E021 | парсер | тело роли принимает may/forbid |
| E022 | парсер | emit ожидает строку |
| E023 | парсер | ожидалось присваивание |
| E024 | парсер | priority не число |
| E025 | парсер | message не строка |
| E026 | парсер | given без = |
| E027 | парсер | неверная конструкция сценария |
| E028 | парсер | link ожидает R-NNN |
| E029 | парсер | неверное значение в множестве |
| E030 | парсер | ожидалось имя поля после точки |
| E031 | парсер | ожидалось имя типа |
| E100 | семантика | дубликат объявления |
| E101 | семантика | неизвестный тип |
| E102 | семантика | неизвестное поле |
| E103 | семантика | несовместимые типы |
| E104 | семантика | условие не Bool |
| E105 | семантика | неизвестное имя |
| E106 | семантика | неизвестное состояние или машина |
| E107 | семантика | неверная цель присваивания |
| E108 | семантика | нельзя присвоить значение такого типа |
| E110 | семантика | неизвестная функция или операция |
| E111 | семантика | неверные аргументы |
| E112 | семантика | дубликат члена enum |
| E113 | семантика | дубликат поля |
| E115 | семантика | apply неизвестного правила |
| E117 | семантика | дубликат события из состояния |
| E118 | семантика | цикл зависимостей правил |
| E119 | семантика | константа не литерал |
| E120 | семантика | типу нужен аргумент |
| E122 | семантика | пустой диапазон |
| E123 | семантика | право и разрешено, и запрещено |
| E130 | валидатор | правило пишет поле дважды |
| E131 | валидатор | конфликт правил |
| E132 | валидатор | литерал вне ограничения |
| W001 | семантика | недостижимое состояние |
| W003 | семантика | неоднозначный член enum |
| W005 | семантика | неизвестное право роли |
| W006 | валидатор | нет начального состояния |
| W010 | валидатор | нет переходов |
| W011 | валидатор | тупиковое состояние |
| W013 | валидатор | перекрытие правил |
| W014 | валидатор | сценарий зовет операцию без перехода |
| W015 | валидатор | нет машин состояний |

## 7. Ручной парсер и восстановление после ошибок

Лексер `core/lexer.py` сканирует строку вручную; регулярные выражения
используются только для идентификаторов и целых чисел. Позиции строки и
столбца обновляются инкрементально при каждом сдвиге.

Парсер `core/parser.py` - рекурсивный спуск с приоритетами операций.
Ошибки не останавливают разбор:

- `_Recover` прерывает текущее объявление или выражение;
- `_synchronize` пропускает токены до `;` или закрывающей скобки на том же
  уровне вложенности;
- пропущенная `;` фиксируется и разбор продолжается;
- цикл объявлений защищен проверкой прогресса, поэтому зависание
  невозможно.

Проверка: `specs/broken5.sforge` содержит пять независимых ошибок, и
`parse` возвращает ровно пять диагностик с позициями. Тест:
`test_parser_collects_exactly_five_errors`.

## 8. Семантический анализатор и валидатор

`core/semantic.py` строит таблицы сущностей, полей, enum, ролей, машин,
правил, инвариантов и сценариев, затем проверяет:

- разрешимость типов и совместимость присваиваний;
- существование полей и членов enum;
- Bool-ность условий;
- сигнатуры операций и аргументов сценария;
- дубликаты и циклы зависимостей правил;
- достижимость состояний.

`core/validator.py` добавляет проверки здравого смысла: конфликты правил,
двойные присваивания, литералы вне ограничений, тупиковые состояния,
сценарии, которые зовут операцию без соответствующего перехода.

Проверка: `specs/semantic3.sforge` содержит три семантические ошибки, и
анализатор возвращает ровно три диагностики до запуска интерпретатора.
Тест: `test_semantic_checker_returns_three_errors`.

## 9. Исполнение

`core/interpreter.py`:

1. вычисляет выражения над миром;
2. исполняет правила (`evaluate_rule`), проверяет `ensures`;
3. прогоняет сценарий, вызывая операции движка;
4. после каждого шага сверяет переходы с машиной и проверяет инварианты.

`runtime/engine.py` - исполняемая модель домена: состояния, время, штрафы,
права, идемпотентность возврата и оплаты, проверки инвариантов. Именно этот
движок используют сгенерированные тесты и property-проверки.

## 10. Как расширять язык

- Новая операция: добавить `OpSignature` в `core/ops.py`, метод `_op_*` в
  `Simulation`, при необходимости соответствие события в `EVENT_ALIASES`.
- Новый тип: расширить `DType` и `_resolve_type`, затем правила вывода в
  `_infer_binary`.
- Новая конструкция: токен в лексере, узел AST, метод `_parse_*`, проверка
  в семантике, узел в `nodes.py` для трассируемости.
