

CREATE TABLE system_config (
    max_active_rooms INTEGER NOT NULL DEFAULT 50 CHECK (max_active_rooms >= 0),
    balance BIGINT DEFAULT 0 NOT NULL CHECK (balance >= 0)
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

CREATE TYPE games AS ENUM ('wheel', 'aviator', 'planka');

CREATE TABLE room_pattern (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game games NOT NULL,
    join_cost BIGINT NOT NULL CHECK (join_cost > 0),

    max_members_count INTEGER NOT NULL DEFAULT 10,
    rank FLOAT NOT NULL,
    min_bots_count INTEGER NOT NULL DEFAULT 1,
    max_bots_count INTEGER NOT NULL DEFAULT 9,

    waiting_lobby_stage INTEGER NOT NULL DEFAULT 60,
    waiting_shop_stage INTEGER NOT NULL DEFAULT 30,

    max_rooms_count INTEGER NOT NULL DEFAULT 50,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    weight INTEGER NOT NULL DEFAULT 1
);



CREATE TYPE room_status AS ENUM (
    'lobby',   -- 1+ игрок. начался таймер до прихода ботов
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
    websocket_access_token TEXT NOT NULL
);

CREATE TABLE room_members (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    boost INTEGER DEFAULT 0
);








INSERT INTO system_config (max_active_rooms, balance) VALUES (50, 9999999999);
--ЗАЩИТА КОНФИГА КАЗИНО
-- Создаём триггерную функцию для запрета INSERT после того, как строка уже есть
CREATE OR REPLACE FUNCTION prevent_extra_insert()
RETURNS TRIGGER AS $$
BEGIN
    IF (SELECT COUNT(*) FROM system_config) >= 1 THEN
        RAISE EXCEPTION 'Таблица system_config уже содержит строку. INSERT запрещён.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Создаём триггер на INSERT
CREATE TRIGGER trg_prevent_extra_insert
BEFORE INSERT ON system_config
FOR EACH ROW EXECUTE FUNCTION prevent_extra_insert();

-- Запрещаем DELETE (навсегда)
CREATE OR REPLACE FUNCTION prevent_delete_config()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'DELETE запрещён в таблице system_config (должна оставаться единственная строка).';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_prevent_delete_config
BEFORE DELETE ON system_config
FOR EACH ROW EXECUTE FUNCTION prevent_delete_config();









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
INSERT INTO room_pattern (game, join_cost, max_members_count, rank, min_bots_count, max_bots_count, waiting_lobby_stage, waiting_shop_stage)
VALUES
('wheel',   100, 10, 1.0, 2, 5, 60, 30),
('aviator', 200, 8,  1.5, 1, 4, 45, 20),
('planka',  50,  6,  0.8, 1, 3, 30, 15);


-- Заполнение комнат
INSERT INTO rooms (room_pattern_id, created_at, started_at, ended_at, status, winner_id, websocket_access_token)
SELECT
    (i % 3) + 1,                         -- равномерно по 3 паттернам
    NOW() - INTERVAL '2 hours',
    NOW() - INTERVAL '90 minutes',
    NOW() - INTERVAL '60 minutes',
    'finished',
    ((i % 10) + 1),                      -- winner всегда user1–user10
    md5(random()::text)
FROM generate_series(1, 100) AS i;


-- Заполнение участников комнат
INSERT INTO room_members (room_id, user_id, boost)
SELECT
    r.id,
    u.user_id,
    (ARRAY[0, 5, 10, 15])[floor(random() * 4 + 1)] AS boost
FROM rooms r
JOIN LATERAL (
    SELECT DISTINCT user_id
    FROM (
        -- победитель ОБЯЗАТЕЛЬНО
        SELECT r.winner_id AS user_id

        UNION

        -- + ещё 2–4 случайных игрока из топ-10
        SELECT (floor(random() * 10) + 1)::int
        FROM generate_series(1, 4)
    ) t
) u ON TRUE
WHERE r.status = 'finished';






