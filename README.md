# Expense Tracker & Bill Splitter

A lightweight personal finance web app built as a portfolio project for a
placement drive at a payment-solutions company. It lets you log expenses,
view a monthly spending summary with a category breakdown chart, manage
(edit/delete) entries, and split a group bill between friends.

## Tech Stack

| Layer     | Technology                          |
|-----------|--------------------------------------|
| Backend   | Python 3 + Flask (JSON REST API)     |
| Database  | SQLite (via Python's built-in `sqlite3`) |
| Frontend  | Plain HTML, CSS, JavaScript (no framework) |
| Charts    | Chart.js (via CDN)                   |

No React, no Node.js, no build tooling — everything runs directly with
Python and a browser, keeping the stack close to what's taught in a typical
DBMS + web-dev curriculum while still resulting in a real, working app.

## Features

- **Add expenses** — amount, category (dropdown), date, and an optional description.
- **Monthly summary** — total spend for a selected month, computed with SQL `SUM()`.
- **Category breakdown chart** — a pie chart (Chart.js) built from a SQL `GROUP BY category` query.
- **Edit / Delete** — inline edit and delete on any expense row.
- **Split Bill calculator** — enter a total and any number of people; it computes
  each person's fair share, handling rounding so the shares always add back up
  exactly to the total. This feature is 100% client-side JavaScript — no
  network calls, no data leaves the browser.
- **Analyze Statement** — upload a bank/card statement PDF and get:
  - Total sent vs. total received (and net)
  - Your biggest single expense
  - A bar chart of your top spending destinations
  - People/merchants you paid more than once, with count + total
  - A review table to selectively import "sent" transactions straight into
    your expense tracker

## Database Design

A single `expenses` table, kept intentionally simple:

```sql
CREATE TABLE expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    amount      REAL NOT NULL CHECK (amount > 0),
    category    TEXT NOT NULL,
    date        TEXT NOT NULL,       -- ISO format: YYYY-MM-DD
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Indexes on `date` and `category` speed up the monthly summary and
category-breakdown queries. Dates are stored as ISO-format text so they sort
correctly with plain string comparison — no date-parsing needed for
range/prefix queries.

## Project Structure

```
expense-tracker/
├── app.py                  # Flask app: page routes + JSON API
├── schema.sql               # SQLite table definition
├── requirements.txt
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── analyze_statement.html
│   └── split_bill.html
└── static/
    ├── css/style.css
    └── js/
        ├── main.js          # Expense CRUD + Chart.js rendering
        ├── statement.js     # PDF statement upload, insights, selective import
        └── split.js         # Client-side bill splitter
```

## How Statement Parsing Works

The `/api/statement/analyze` endpoint uses **pdfplumber** to extract tables
from the uploaded PDF (no OCR — it only reads embedded text, so scanned
image PDFs won't work). For each table found:

1. **Header detection** — scans the header row for keywords (`date`,
   `debit`/`withdrawal`, `credit`/`deposit`, or a single `amount` column
   plus a `type`/`Dr`/`Cr` column) to figure out which column is which,
   since real statements from different banks name these differently.
2. **Row parsing** — each row's date and amount are normalized (multiple
   date formats are tried; currency symbols/commas are stripped from
   amounts) and classified as `"sent"` (debit) or `"received"` (credit).
3. **Category guessing** — a simple keyword match against the transaction
   description (e.g. "swiggy" → Food, "uber" → Travel) fills in a starting
   category, which the user can still change before importing.
4. **Aggregation** — transactions are grouped by description text to find
   repeat recipients (count + total sent), the single largest expense, and
   overall totals sent vs. received.

Nothing is written to the database during analysis — the results are shown
as a **preview** the user reviews (and can edit categories on) before
choosing to import specific "sent" transactions into the expense tracker via
the existing `/api/expenses` endpoint.

## How to Run Locally

1. **Clone / download** this project folder.

2. **Create a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate      # on Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**:
   ```bash
   python app.py
   ```
   On first run, `app.py` automatically creates `expense_tracker.db` using
   `schema.sql` — you don't need to run anything manually.

5. Open your browser to **http://127.0.0.1:5000**

To reset the database at any point, just delete `expense_tracker.db` and
restart the app — it will be recreated automatically.

## API Endpoints

| Method | Route                     | Purpose                              |
|--------|----------------------------|---------------------------------------|
| GET    | `/api/expenses`            | List all expenses (optional `?month=YYYY-MM`) |
| POST   | `/api/expenses`            | Add a new expense                    |
| PUT    | `/api/expenses/<id>`       | Update an existing expense           |
| DELETE | `/api/expenses/<id>`       | Delete an expense                    |
| GET    | `/api/summary?month=YYYY-MM` | Total spend + category breakdown for a month |
| POST   | `/api/statement/analyze`   | Upload a statement PDF, get parsed transactions + insights (no DB write) |

## Ideas to Extend This Yourself

A few small, self-contained features worth adding to make this genuinely
yours (and good talking points for an interview):

1. **Budget limits & alerts** — let the user set a monthly budget per category,
   and show a warning banner (or turn the total red) when they exceed it.
   Good practice with conditional rendering and a small `budgets` table (or
   even just `localStorage` for a v1).

2. **Export to CSV** — add a "Download CSV" button that hits a new
   `/api/expenses/export` route, which uses Python's built-in `csv` module
   to stream a `.csv` file back with `Response(..., mimetype='text/csv')`.
   Great way to demonstrate file responses in Flask.

3. **Recurring expenses** — add an `is_recurring` flag and a "duplicate to
   next month" button on each row, so rent/subscriptions don't need to be
   re-entered manually every month.

4. *(Slightly bigger, optional)* **Multi-currency support** — store a
   `currency` column and a fixed exchange-rate lookup table, and show totals
   converted to a "home currency." Ties in nicely with the payments domain.

## Notes on Design Decisions (for interview prep)

- **Server-side validation duplicates client-side validation** intentionally —
  the frontend checks exist for UX (instant feedback), the backend checks
  exist for security (a malicious or buggy client could call the API directly).
- **Parameterized SQL queries** (`?` placeholders) are used everywhere to
  prevent SQL injection.
- **Split-bill math works in integer paise**, not floating-point rupees, to
  avoid rounding errors — the same principle real payment systems use when
  handling money (avoid float arithmetic for currency).
- **One Flask app, no ORM** — raw SQL was used deliberately here to show
  direct SQL fluency (joins, aggregates, indexing) rather than hiding it
  behind an ORM, which fits a scope like this.