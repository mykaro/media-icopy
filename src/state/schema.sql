-- src/state/schema.sql

-- Таблиця для відстеження вже скопійованих файлів (для ідемпотентності)
CREATE TABLE IF NOT EXISTS copied_files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    relative_path TEXT NOT NULL UNIQUE,
    size_bytes    INTEGER NOT NULL,
    copied_at     REAL NOT NULL    -- Unix timestamp
);

-- Таблиця для зберігання стану поточної сесії копіювання
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      REAL NOT NULL,
    state           TEXT NOT NULL,  -- значення з SessionState enum
    total_files     INTEGER,
    batch_index     INTEGER DEFAULT 0,
    source_root     TEXT NOT NULL,
    dest_root       TEXT NOT NULL
);

-- Таблиця для черги повторних спроб (retry queue)
CREATE TABLE IF NOT EXISTS retry_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER REFERENCES sessions(id),
    relative_path   TEXT NOT NULL,
    object_id       TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    attempt         INTEGER DEFAULT 0,
    last_error      TEXT,
    scheduled_at    REAL    -- Unix timestamp наступної спроби
);

-- Індекси для швидкого пошуку
CREATE INDEX IF NOT EXISTS idx_copied_path ON copied_files(relative_path);
CREATE INDEX IF NOT EXISTS idx_retry_session ON retry_queue(session_id, scheduled_at);
