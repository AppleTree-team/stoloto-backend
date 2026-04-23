# Stoloto Backend (FastAPI)

Бэкенд для “комнат” (`rooms`) с этапами `waiting → lobby → shop → running → finished`, SSE‑стримами для `lobby` и `shop`, учётом средств игроков и казино, а также админскими ручками для аудита и поддержки.

## Быстрый старт (Docker Compose)

1) Создай `.env` на основе `.env.example`.
2) Запусти сервисы:

```bash
docker-compose up -d --build --force-recreate
```

API будет доступен на `http://localhost:8000`.

Проверка: `GET /health`.

## Авторизация

Авторизация через cookie `session_id` (JWT).

- `POST /api/auth/login` (body: `{ "username": "...", "password": "..." }`)
  - при успехе выставляет httpOnly cookie `session_id`
- `POST /api/auth/logout`

Все защищённые ручки ожидают, что cookie отправляется браузером автоматически.

## Основные сущности

- `room_pattern` — правила комнаты (игра, цена входа, вместимость, рейк, таймеры, лимиты, вес для матчмейкинга, стоимость буста).
- `rooms` — инстансы комнат.
- `room_members` — “слоты” участников. Один пользователь может купить несколько слотов. Буст покупается на конкретный слот (`room_members.id`).
- `system_config` — глобальные настройки (лимит активных комнат, баланс казино, включение ботов, лимиты ставок).
- `ledger_entries` — журнал движения средств (account: `user/casino/escrow`).
- `room_escrow` — агрегированный фонд комнаты (stake/boost) для отображения и расчётов.

## Этапы комнаты

- `waiting`: комната создана, игроков может ещё не быть.
- `lobby`: ожидание набора участников (SSE).
- `shop`: этап покупок доп. слотов и бустов (SSE). Покупки ограничены правилом “шанс не может стать > 50%”.
- `running`: старт игры.
- `finished`: победитель записан в `rooms.winner_id`, время окончания — `rooms.ended_at`.

Важно: если никто не подключился по SSE, процесс всё равно не “ломается” — стадии продвигаются внутренним stage‑менеджером.

## SSE (как подключать фронт)

### Lobby

`GET /api/room/{token}/lobby` (text/event-stream)

События:
- `tick`: таймер + статусы + фонды + шанс победы
- `lobby_end`: переход в `shop`
- `error`

### Shop

`GET /api/room/{token}/shop/` (text/event-stream)

События:
- `tick`: таймер + фонды + шанс + `my_slots`
- `slots_update`: изменение количества мест/веса
- `game_start`
- `game_result`
- `error`

Важно: в `tick` и в `GET /api/room/{token}` сервер отдаёт `my_slots: [{ slot_id, boost }]`, чтобы фронт всегда знал `slot_id` для покупки буста.

## Комнаты (пользовательские ручки)

- `POST /api/room/search` — найти/создать комнату под фильтр (учитывает лимиты активных комнат и лимиты паттерна).
  - если пользователь уже в активной комнате, вернёт `already_in_game=true`.
- `GET /api/room/{token}` — информация о комнате + `my_slots` текущего пользователя.
- `GET /api/room/{token}/victory_chance` — подробный расчёт шансов (слоты/бусты).

### Покупки (shop)

- `POST /api/room/{token}/shop/buy/slot` — купить доп. слот, ответ содержит `slot_id`.
- `POST /api/room/{token}/shop/buy/boost?slot_id=...&boost=...` — купить буст на слот.

## Как считаются бусты, вес и шанс

Модель “буст = процент к слоту”, а не “процент к шансу”.

- Базовый “вес” одного слота = `100`.
- Если `boost=5`, вес слота становится `105` (то есть +5% к слоту).
- Общий вес комнаты = сумма весов всех слотов.
- Шанс пользователя = `user_weight / total_weight`, где `user_weight` — сумма весов слотов пользователя.

### Два процента на фронте

Бэкенд отдаёт две метрики:

- `chance_current_percent`: шанс **среди текущих участников** (по текущему `total_weight`).
- `chance_capacity_percent`: шанс “от полной вместимости”, как будто все свободные места будут заняты обычными слотами с весом `100`.

`chance_capacity_percent` удобнее для UI, чтобы шанс не “скакал” от того, что в комнате пока мало людей.

## Выбор победителя (как устроено)

Победитель выбирается случайно, но с “взвешиванием” по весам слотов:

1) Для каждого слота (`room_members`) рассчитывается `weight = 100 + boost`.
2) Считается `total_weight = SUM(weight)`.
3) Генерируется случайное число `r` от `1` до `total_weight`.
4) Слоты сортируются по `id`, считается накопительная сумма `cum_weight`.
5) Победителем становится первый слот, у которого `cum_weight >= r`. Победитель — `user_id` этого слота.

Это эквивалентно “лотерее”: чем больше суммарный вес твоих слотов, тем выше вероятность.

Где в коде: `app/services/room_service.py` в финализации игры (там же запись `winner_id`, `ended_at` и проводки в ledger).

## Деньги: почему система надёжная (escrow + ledger)

Система разделяет:

- **Баланс пользователя** (`users.balance`) — то, что пользователь реально может тратить.
- **Фонд комнаты (escrow)** (`room_escrow`) — куда попадают деньги от ставок/покупок до момента определения победителя.
- **Баланс казино** (`system_config.casino_balance`) — бюджет казино (в том числе на ботов и ручные корректировки).
- **Журнал операций** (`ledger_entries`) — аудит “кто, кому, сколько и почему”.

Типичный поток:

1) Вход/покупка слота/покупка буста:
   - списываем у пользователя (ledger: `account=user`, amount отрицательный)
   - начисляем в escrow (ledger: `account=escrow`, amount положительный)
2) Завершение игры:
   - из escrow выходит сумма фонда (ledger: `account=escrow`, entry_type=`escrow_out`, amount отрицательный)
   - победителю начисляется выплата (ledger: `account=user`, entry_type=`payout`, amount положительный)
   - казино получает доход (ledger: `account=casino`, entry_type=`casino_income`, amount положительный)

За счёт `ledger_entries` можно разбирать спорные ситуации и делать сверку.

## Админка: “приколы” и возможности

Админские ручки дают то, что реально нужно в казино‑продукте:

### 1) Управление рисками

- глобальный лимит активных комнат (`max_active_rooms`)
- включение/выключение ботов (`bots_enabled`)
- лимиты ставок по `join_cost` (через `min_join_cost/max_join_cost` + валидация паттернов)

### 2) Операции и поддержка

- поиск пользователя/комнаты по id/token
- карточка комнаты: участники, слоты, бусты, фонды, ledger
- ручное закрытие комнаты (force finish) и ручной рефанд (force refund)
- ручные корректировки баланса user↔casino с записью в ledger

### 3) Логи и аудит

- фильтруемый ledger (`room_id`, `user_id`, `account`, `entry_type`, даты)
- экспорт ledger в CSV
- простая сверка `casino_balance` с суммой по `ledger_entries` (для быстрого sanity‑check)
- страница anomalies (например, “running без участников”)

## Админка (API)

Все админские ручки требуют `is_admin=true` (иначе 403).

### Конфиг/риски

- `GET /api/admin/config`
- `PATCH /api/admin/config` (например: `max_active_rooms`, `casino_balance`, `bots_enabled`, `min_join_cost`, `max_join_cost`)

### Пользователи

- `GET /api/admin/users/search?q=...`
- `GET /api/admin/users/{user_id}/history`
- `GET /api/admin/users/{user_id}/current_game`
- `POST /api/admin/users/{user_id}/adjust_balance` (перевод user↔casino с записью в ledger)

### Комнаты/история

- `GET /api/admin/rooms` (активные/по статусу)
- `GET /api/admin/rooms/history` (finished за период)
- `GET /api/admin/rooms/search?token=...|room_id=...`
- `GET /api/admin/rooms/{room_id}/card` (карточка комнаты: участники/фонды/ledger)
- `POST /api/admin/rooms/{room_id}/force_finish_running`
- `POST /api/admin/rooms/{room_id}/force_refund`

### Ledger / аудит

- `GET /api/admin/ledger` (фильтры: `room_id`, `user_id`, `account`, `entry_type`, даты, limit/offset)
- `GET /api/admin/ledger/export.csv` (то же, но CSV)
- `GET /api/admin/reconcile/casino` (быстрая сверка casino_balance vs сумма по ledger)
- `GET /api/admin/anomalies`

## Почему это хорошая архитектура (плюсы системы)

- **Прозрачные деньги**: escrow + ledger дают предсказуемые проводки и объяснимость выплат.
- **Идемпотентность и конкуренция**: критичные действия обёрнуты в транзакции и advisory‑locks, чтобы не “добавляло дважды”.
- **SSE как UX, а не зависимость**: игровая логика не зависит от подключений клиентов.
- **Масштабирование**: можно поднимать несколько инстансов (ключевые операции защищены блокировками/БД‑проверками).
- **Админка из коробки**: поиск, история, аудит, рефанды/корректировки, экспорт — всё на API‑уровне.

## Конфигурация (.env)

Смотри `.env.example`:

- Postgres: `DB_*`
- Таймзона БД: `DB_TIMEZONE` (по умолчанию `Europe/Moscow`)
- JWT: `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_HOURS`
- Redis: `REDIS_URL`
- CORS: `CORS_ORIGINS`

