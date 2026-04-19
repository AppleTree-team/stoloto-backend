CREATE TABLE casino_balance (
    id INTEGER PRIMARY KEY DEFAULT 1,
    balance BIGINT DEFAULT 0 NOT NULL CHECK (balance >= 0)
);

CREATE TABLE users (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password TEXT NOT NULL,
    balance BIGINT DEFAULT 0 NOT NULL CHECK (balance >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_bot BOOLEAN DEFAULT FALSE
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
    waiting_shop_stage INTEGER NOT NULL DEFAULT 30
);



CREATE TYPE room_status AS ENUM (
    'waiting', -- комната создана но игроков 0
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

    status room_status NOT NULL DEFAULT 'waiting',

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
