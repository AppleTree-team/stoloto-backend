
CREATE TABLE system_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    max_active_rooms INTEGER NOT NULL DEFAULT 50 CHECK (max_active_rooms >= 0),
    casino_balance BIGINT NOT NULL DEFAULT 999999999 CHECK (casino_balance >= 0),
    bots_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    min_join_cost BIGINT NOT NULL DEFAULT 1 CHECK (min_join_cost >= 0),
    max_join_cost BIGINT NOT NULL DEFAULT 1000000000 CHECK (max_join_cost >= 0)
);

CREATE TABLE users (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password TEXT NOT NULL,
    balance BIGINT DEFAULT 0 NOT NULL CHECK (balance >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_bot BOOLEAN DEFAULT FALSE,
    is_admin BOOLEAN DEFAULT FALSE
);

CREATE TYPE games AS ENUM ('wheel', 'aviator', 'plinko', 'minesweeper');

CREATE TABLE room_pattern (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game games NOT NULL,
    join_cost BIGINT NOT NULL CHECK (join_cost > 0),
    deleted_at TIMESTAMP,

    max_members_count INTEGER NOT NULL DEFAULT 10,
    rank FLOAT NOT NULL,

    waiting_lobby_stage INTEGER NOT NULL DEFAULT 60,
    waiting_shop_stage INTEGER NOT NULL DEFAULT 30,

    max_rooms_count INTEGER NOT NULL DEFAULT 50,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    weight INTEGER NOT NULL DEFAULT 1 CHECK (weight > 0),

    -- Финансы
    boost_cost_per_point BIGINT NOT NULL DEFAULT 10 CHECK (boost_cost_per_point >= 0),
    winner_payout_percent INTEGER NOT NULL DEFAULT 100 CHECK (winner_payout_percent BETWEEN 0 AND 100)
);

--Вставляем запись в конфигурацию казино
INSERT INTO system_config (id, max_active_rooms, casino_balance)
VALUES (1, 50, 999999999)
ON CONFLICT (id) DO NOTHING;



CREATE TYPE room_status AS ENUM (
    'waiting', -- комната не активна и ожидает первого игрока
    'lobby',   -- начальнаое состояние,если >=1 игрок. начался таймер до прихода ботов
    'shop',    -- этап закупки бустов и доп мест в комнате. после этого этапа добавляются боты
    'running', -- игра играется
    'finished' -- игра завершена
);



CREATE TABLE rooms (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    room_pattern_id INTEGER NOT NULL REFERENCES room_pattern(id) ON DELETE CASCADE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,

    status room_status NOT NULL DEFAULT 'lobby',

    winner_id INTEGER REFERENCES users(id),
    access_token TEXT NOT NULL
);

CREATE TABLE room_members (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    boost INTEGER DEFAULT 0
);

CREATE TABLE room_escrow (
    room_id INTEGER PRIMARY KEY REFERENCES rooms(id) ON DELETE CASCADE,
    amount BIGINT NOT NULL DEFAULT 0 CHECK (amount >= 0),
    stake_amount BIGINT NOT NULL DEFAULT 0 CHECK (stake_amount >= 0),
    boost_amount BIGINT NOT NULL DEFAULT 0 CHECK (boost_amount >= 0),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ledger_entries (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    account VARCHAR(32) NOT NULL, -- user / casino / escrow
    entry_type VARCHAR(64) NOT NULL,
    amount BIGINT NOT NULL, -- + credit, - debit
    meta JSONB NOT NULL DEFAULT '{}'::jsonb
);











--Для теста сделаем генирацию пользователей с одним паролем
-- 100 обычных пользователей
INSERT INTO users (username, password, balance, is_bot)
SELECT
    'user' || i,
    'a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3',
    10000,
    FALSE
FROM generate_series(1, 100) AS i;

--Для отладки. При деплое изменить!
INSERT INTO users (username, password, balance, is_admin)
VALUES
    ('admin',
     'a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3',
     0,True);


-- 100 ботов
INSERT INTO users (username, password, balance, is_bot)
SELECT
    'bot' || i,
    'a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3',
    0,
    TRUE
FROM generate_series(1, 100) AS i;

-- Заполнение таблицы паттернов
INSERT INTO room_pattern (game, join_cost, max_members_count, rank, waiting_lobby_stage, waiting_shop_stage, boost_cost_per_point, winner_payout_percent)
VALUES
('wheel',   100, 10, 20.0, 60, 30, 10, 100),
('aviator', 200, 8,  20.0, 45, 20, 10, 100),
('plinko',  50,  6,  20.0, 30, 15, 10, 100),
('minesweeper', 50, 6, 20.0, 30, 15, 10, 100);





