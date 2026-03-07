-- name: 002_warns
PRAGMA foreign_keys = ON;

ALTER TABLE users
ADD COLUMN warn_count INTEGER DEFAULT 0;

CREATE TABLE
    IF NOT EXISTS warns (
        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
        user_id INTEGER NOT NULL,
        reason TEXT,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expired BOOLEAN DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    );

CREATE TRIGGER update_warns_count_insert AFTER INSERT ON warns BEGIN
UPDATE users
SET
    warn_count = (
        SELECT
            COUNT(*)
        FROM
            warns
        WHERE
            warns.user_id = NEW.user_id
            AND (added_at > TIMESTAMP('now', '-30 days'))
    )
WHERE
    user_id = NEW.user_id;

END;

CREATE TRIGGER update_warns_count_delete AFTER DELETE ON warns BEGIN
UPDATE users
SET
    warn_count = (
        SELECT
            COUNT(*)
        FROM
            warns
        WHERE
            warns.user_id = OLD.user_id
            AND (added_at > TIMESTAMP('now', '-30 days'))
    )
WHERE
    user_id = OLD.user_id;

END;