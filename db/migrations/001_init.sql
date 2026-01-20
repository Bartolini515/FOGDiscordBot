-- name: 001_init
PRAGMA foreign_keys = ON;

CREATE TABLE
    IF NOT EXISTS ranks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        role_id INTEGER,
        required_missions INTEGER NOT NULL
    );

CREATE TABLE
    IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY UNIQUE,
        username TEXT NOT NULL,
        level INTEGER DEFAULT 1 CHECK (level BETWEEN 1 AND 100),
        experience INTEGER DEFAULT 155,
        rank_id INTEGER DEFAULT 1,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_message_at TIMESTAMP DEFAULT NULL,
        on_guild BOOLEAN DEFAULT 1,
        FOREIGN KEY (rank_id) REFERENCES ranks (id) ON DELETE SET DEFAULT
    );

CREATE TABLE
    IF NOT EXISTS blacklist (
        user_id INTEGER PRIMARY KEY UNIQUE,
        reason TEXT,
        end_at TIMESTAMP DEFAULT NULL,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    );

CREATE TABLE
    IF NOT EXISTS attendance (
        user_id INTEGER PRIMARY KEY UNIQUE,
        last_mission_date DATE,
        all_time_missions INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    );

CREATE TABLE
    IF NOT EXISTS missions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        channel_id INTEGER NOT NULL UNIQUE,
        date DATE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        creator_user_id INTEGER,
        ping_role_id INTEGER,
        FOREIGN KEY (creator_user_id) REFERENCES users (user_id) ON DELETE SET NULL
    );

CREATE TABLE
    IF NOT EXISTS squads (
        message_id INTEGER PRIMARY KEY UNIQUE,
        mission_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        FOREIGN KEY (mission_id) REFERENCES missions (id) ON DELETE CASCADE
    );

CREATE TABLE
    IF NOT EXISTS slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        mission_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        user_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE SET NULL,
        FOREIGN KEY (mission_id) REFERENCES missions (id) ON DELETE CASCADE,
        FOREIGN KEY (message_id) REFERENCES squads (message_id) ON DELETE CASCADE
    );

CREATE TABLE
    IF NOT EXISTS trainings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        channel_id INTEGER NOT NULL UNIQUE,
        message_id INTEGER UNIQUE,
        date DATE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        creator_user_id INTEGER,
        FOREIGN KEY (creator_user_id) REFERENCES users (user_id) ON DELETE SET NULL
    );

CREATE TABLE
    IF NOT EXISTS training_signed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        training_id INTEGER NOT NULL,
        user_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE SET NULL,
        FOREIGN KEY (training_id) REFERENCES trainings (id) ON DELETE CASCADE
    );

CREATE TABLE
    IF NOT EXISTS ticket_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );

CREATE TABLE
    IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL UNIQUE,
        user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status BOOLEAN DEFAULT 1,
        type_id INTEGER,
        title TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE SET NULL,
        FOREIGN KEY (type_id) REFERENCES ticket_types (id) ON DELETE SET NULL
    );

CREATE TABLE
    IF NOT EXISTS ticket_create_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL UNIQUE,
        message_id INTEGER NOT NULL UNIQUE,
        categories TEXT
    );

INSERT
OR IGNORE INTO ranks (id, name, role_id, required_missions)
VALUES
    (1, 'Rekrut', 1458467452278149338, 0),
    (2, 'Operator I', 1458466593737801739, 10),
    (3, 'Operator II', 1458466570119680163, 60),
    (4, 'Operator III', 1458466533788618762, 90),
    (5, 'Operator IV', 1458466475206643965, 140),
    (6, 'Operator V', 1458466427618201751, 200);

INSERT
OR IGNORE INTO ticket_types (id, name)
VALUES
    (1, 'mission'),
    (2, 'proposal'),
    (3, 'custom');