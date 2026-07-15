-- Single table design, kept intentionally simple for this smaller project.
DROP TABLE IF EXISTS expenses;

CREATE TABLE expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    amount      REAL NOT NULL CHECK (amount > 0),
    category    TEXT NOT NULL,
    date        TEXT NOT NULL,        -- stored as 'YYYY-MM-DD' (ISO format, sorts correctly as text)
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Speeds up the monthly summary / category breakdown queries,
-- which both filter and group on these columns.
CREATE INDEX idx_expenses_date ON expenses(date);
CREATE INDEX idx_expenses_category ON expenses(category);
