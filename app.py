import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pdfplumber
from flask import Flask, g, render_template, request, jsonify

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "expense_tracker.db"
SCHEMA = BASE_DIR / "schema.sql"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    """
    Open one SQLite connection per request and stash it on Flask's 'g'
    object so repeated calls within the same request reuse it instead
    of opening a fresh connection each time.
    """
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row  # lets us access columns by name, e.g. row["amount"]
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    """Flask calls this automatically after every request finishes."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Run schema.sql once to (re)create the expenses table."""
    with app.app_context():
        db = get_db()
        with open(SCHEMA, "r") as f:
            db.executescript(f.read())
        db.commit()


def row_to_dict(row):
    return {
        "id": row["id"],
        "amount": row["amount"],
        "category": row["category"],
        "date": row["date"],
        "description": row["description"],
    }


# ---------------------------------------------------------------------------
# PDF import helpers
# ---------------------------------------------------------------------------
# Very small keyword map used to guess a category when the PDF doesn't
# have its own category column. Deliberately simple -- a fun place to
# extend later (see README "Ideas to Extend").
CATEGORY_KEYWORDS = {
    "Food": ["restaurant", "food", "cafe", "coffee", "swiggy", "zomato", "dine", "eat",
             "juice", "bakery", "sweets", "kitchen", "chats"],
    "Travel": ["uber", "ola", "taxi", "flight", "airlines", "fuel", "petrol", "irctc",
               "train", "redbus", "bus"],
    "Utilities": ["electricity", "water bill", "gas", "internet", "wifi", "broadband",
                  "recharge", "prepaid", "jio", "airtel", "vi ", "dth", "sun direct"],
    "Entertainment": ["movie", "netflix", "spotify", "cinema", "pvr", "inox", "prime video"],
    "Shopping": ["amazon", "flipkart", "mall", "store", "myntra", "mart", "meesho",
                 "ekart", "zepto", "blinkit"],
    "Rent": ["rent", "landlord"],
}

DATE_FORMATS = [
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
    "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%b %d %Y",
    "%d %b, %Y", "%d %B, %Y",
]


def guess_category(text):
    """Keyword-match free text against CATEGORY_KEYWORDS. Defaults to 'Other'."""
    lowered = (text or "").lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return category
    return "Other"


def try_parse_date(value):
    """Attempts several common date formats; returns 'YYYY-MM-DD' or None."""
    if not value:
        return None
    value = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def try_parse_amount(value):
    """
    Strips currency symbols/commas and parses a float.
    Treats parenthesized numbers, e.g. '(500.00)', as negative (common in
    statements for credits/refunds) -- we take the absolute value since
    this app only tracks outgoing expenses.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    is_negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^\d.\-]", "", text.replace(",", ""))
    if not cleaned or cleaned in ("-", "."):
        return None
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    return abs(amount) if amount != 0 else None


def parse_statement_table(table):
    """
    Given a table extracted by pdfplumber, tries to identify date,
    description, and either separate debit/credit columns OR a single
    amount column (with a Dr/Cr type indicator) from the header row.

    Returns a list of transaction dicts:
        {date, description, amount, direction}
    where direction is "sent" (money out / debit) or "received" (money in / credit).

    Returns [] if it can't confidently find a date column plus at least
    one amount-ish column.
    """
    if not table or len(table) < 2:
        return []

    header = [(cell or "").strip().lower() for cell in table[0]]
    col_map = {}
    for i, cell in enumerate(header):
        if "date" not in col_map and "date" in cell:
            col_map["date"] = i
        elif "description" not in col_map and any(k in cell for k in
                ["description", "narration", "details", "merchant", "particulars", "payee"]):
            col_map["description"] = i
        elif "debit" not in col_map and any(k in cell for k in
                ["debit", "withdrawal", "paid out", "dr amount"]):
            col_map["debit"] = i
        elif "credit" not in col_map and any(k in cell for k in
                ["credit", "deposit", "paid in", "cr amount"]):
            col_map["credit"] = i
        elif "amount" not in col_map and any(k in cell for k in ["amount", "amt"]):
            col_map["amount"] = i
        elif "type" not in col_map and any(k in cell for k in ["type", "dr/cr", "cr/dr"]):
            col_map["type"] = i

    has_amount_source = "debit" in col_map or "credit" in col_map or "amount" in col_map
    if "date" not in col_map or not has_amount_source:
        return []

    results = []
    for row in table[1:]:
        if not row or len(row) <= max(col_map.values()):
            continue

        date_val = try_parse_date(row[col_map["date"]])
        if not date_val:
            continue

        description = ""
        if "description" in col_map and row[col_map["description"]]:
            description = row[col_map["description"]].strip()

        amount = None
        direction = None

        # Case A: statement has separate debit/credit columns (most common format)
        if "debit" in col_map or "credit" in col_map:
            debit_val = try_parse_amount(row[col_map["debit"]]) if "debit" in col_map else None
            credit_val = try_parse_amount(row[col_map["credit"]]) if "credit" in col_map else None
            if debit_val:
                amount, direction = debit_val, "sent"
            elif credit_val:
                amount, direction = credit_val, "received"

        # Case B: single amount column, direction inferred from a type column
        # or from "Cr"/"Dr" suffix inside the amount cell itself.
        elif "amount" in col_map:
            raw_amount_cell = str(row[col_map["amount"]] or "")
            amount = try_parse_amount(raw_amount_cell)
            if amount:
                type_text = ""
                if "type" in col_map and row[col_map["type"]]:
                    type_text = str(row[col_map["type"]]).lower()
                combined = (type_text + " " + raw_amount_cell).lower()
                if "cr" in combined and "dr" not in combined:
                    direction = "received"
                else:
                    direction = "sent"  # default assumption: unmarked amounts are spending

        if not amount or not direction:
            continue

        results.append({
            "date": date_val,
            "description": description,
            "amount": amount,
            "direction": direction,
            "category": guess_category(description),
        })

    return results


# UPI apps (Google Pay, PhonePe, Paytm, etc.) typically export statements
# as repeating text lines rather than a ruled table, e.g.:
#   "01 Apr, 2026 Paid to VMK ENTERPRISES ₹10"
# pdfplumber's extract_tables() finds nothing on these, so this pattern
# matches that line shape directly out of the extracted text as a fallback.
UPI_LINE_PATTERN = re.compile(
    r"^(?P<date>\d{1,2} [A-Za-z]{3},\s*\d{4})\s+"
    r"(?P<direction>Paid to|Received from)\s+"
    r"(?P<name>.+?)\s+"
    r"₹(?P<amount>[\d,]+\.?\d*)\s*$",
    re.MULTILINE,
)


def parse_upi_statement_text(text):
    """
    Fallback parser for UPI-app statement PDFs where transactions appear
    as plain text lines instead of inside a ruled table. Returns the same
    transaction dict shape as parse_statement_table() so the rest of the
    pipeline (insights, import) doesn't need to know which parser ran.
    """
    results = []
    for match in UPI_LINE_PATTERN.finditer(text):
        date_val = try_parse_date(match.group("date"))
        amount_val = try_parse_amount(match.group("amount"))
        if not date_val or not amount_val:
            continue

        direction = "sent" if match.group("direction") == "Paid to" else "received"
        name = match.group("name").strip()

        results.append({
            "date": date_val,
            "description": name,
            "amount": amount_val,
            "direction": direction,
            "category": guess_category(name),
        })
    return results


def build_statement_insights(transactions):
    """
    Aggregates a list of parsed transactions into the insights shown on
    the Analyze Statement page: totals, recurring recipients, top spend
    destination, and the single biggest expense.
    """
    sent = [t for t in transactions if t["direction"] == "sent"]
    received = [t for t in transactions if t["direction"] == "received"]

    total_sent = round(sum(t["amount"] for t in sent), 2)
    total_received = round(sum(t["amount"] for t in received), 2)

    # Group "sent" transactions by recipient (the description text) so we
    # can see who/where money repeatedly went to.
    recipients = {}
    for t in sent:
        key = t["description"].strip().lower() or "unknown"
        if key not in recipients:
            recipients[key] = {"name": t["description"] or "Unknown", "count": 0, "total": 0.0}
        recipients[key]["count"] += 1
        recipients[key]["total"] += t["amount"]

    recipient_list = list(recipients.values())
    for r in recipient_list:
        r["total"] = round(r["total"], 2)

    top_by_spend = sorted(recipient_list, key=lambda r: r["total"], reverse=True)
    top_by_frequency = sorted(recipient_list, key=lambda r: r["count"], reverse=True)

    biggest_expense = max(sent, key=lambda t: t["amount"], default=None)

    return {
        "total_sent": total_sent,
        "total_received": total_received,
        "net": round(total_received - total_sent, 2),
        "top_recipients_by_spend": top_by_spend[:5],
        "top_recipients_by_frequency": [r for r in top_by_frequency if r["count"] > 1][:5],
        "biggest_expense": biggest_expense,
        "transaction_count": len(transactions),
    }


# ---------------------------------------------------------------------------
# Page routes (render HTML templates)
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze-statement")
def analyze_statement():
    return render_template("analyze_statement.html")


@app.route("/split-bill")
def split_bill():
    return render_template("split_bill.html")


# ---------------------------------------------------------------------------
# JSON API routes (called by static/js/main.js via fetch)
# ---------------------------------------------------------------------------
@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    """
    Returns all expenses, most recent first.
    Supports optional ?month=YYYY-MM filtering, used by the summary view.
    """
    month = request.args.get("month")  # e.g. "2026-07"
    db = get_db()

    if month:
        rows = db.execute(
            "SELECT * FROM expenses WHERE date LIKE ? ORDER BY date DESC, id DESC",
            (f"{month}%",),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM expenses ORDER BY date DESC, id DESC"
        ).fetchall()

    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/expenses", methods=["POST"])
def add_expense():
    data = request.get_json(force=True)

    amount = data.get("amount")
    category = (data.get("category") or "").strip()
    date = (data.get("date") or "").strip()
    description = (data.get("description") or "").strip()

    # Server-side validation -- never trust the client alone.
    if not amount or float(amount) <= 0:
        return jsonify({"error": "Amount must be a positive number"}), 400
    if not category:
        return jsonify({"error": "Category is required"}), 400
    if not date:
        return jsonify({"error": "Date is required"}), 400
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Date must be in YYYY-MM-DD format"}), 400

    db = get_db()
    cursor = db.execute(
        "INSERT INTO expenses (amount, category, date, description) VALUES (?, ?, ?, ?)",
        (float(amount), category, date, description),
    )
    db.commit()

    new_row = db.execute(
        "SELECT * FROM expenses WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return jsonify(row_to_dict(new_row)), 201


@app.route("/api/expenses/<int:expense_id>", methods=["PUT"])
def update_expense(expense_id):
    data = request.get_json(force=True)
    db = get_db()

    existing = db.execute(
        "SELECT * FROM expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    if existing is None:
        return jsonify({"error": "Expense not found"}), 404

    amount = data.get("amount", existing["amount"])
    category = data.get("category", existing["category"])
    date = data.get("date", existing["date"])
    description = data.get("description", existing["description"])

    if float(amount) <= 0:
        return jsonify({"error": "Amount must be a positive number"}), 400

    db.execute(
        """UPDATE expenses
           SET amount = ?, category = ?, date = ?, description = ?
           WHERE id = ?""",
        (float(amount), category, date, description, expense_id),
    )
    db.commit()

    updated = db.execute(
        "SELECT * FROM expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    return jsonify(row_to_dict(updated))


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    db = get_db()
    existing = db.execute(
        "SELECT id FROM expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    if existing is None:
        return jsonify({"error": "Expense not found"}), 404

    db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    db.commit()
    return jsonify({"message": "Deleted"}), 200


@app.route("/api/summary", methods=["GET"])
def get_summary():
    """
    Returns:
      - total spending for the given month
      - category-wise breakdown for that month (used to draw the pie/bar chart)
    Defaults to the current month if none is passed.
    """
    month = request.args.get("month") or datetime.now().strftime("%Y-%m")
    db = get_db()

    total_row = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE date LIKE ?",
        (f"{month}%",),
    ).fetchone()

    category_rows = db.execute(
        """SELECT category, SUM(amount) AS total
           FROM expenses
           WHERE date LIKE ?
           GROUP BY category
           ORDER BY total DESC""",
        (f"{month}%",),
    ).fetchall()

    return jsonify({
        "month": month,
        "total": total_row["total"],
        "by_category": [
            {"category": r["category"], "total": r["total"]} for r in category_rows
        ],
    })


@app.route("/api/statement/analyze", methods=["POST"])
def analyze_statement_pdf():
    """
    Accepts an uploaded bank/card statement PDF, extracts every
    transaction it can find (with date, description, amount, and whether
    it was money sent or received), and returns both the raw transaction
    list and aggregated insights. Nothing is written to the database here
    -- the frontend lets the user pick which "sent" transactions to
    import afterward via the existing /api/expenses endpoint.
    """
    uploaded = request.files.get("pdf")
    if not uploaded or uploaded.filename == "":
        return jsonify({"error": "No PDF file uploaded"}), 400
    if not uploaded.filename.lower().endswith(".pdf"):
        return jsonify({"error": "File must be a PDF"}), 400

    try:
        with pdfplumber.open(uploaded) as pdf:
            transactions = []
            full_text = ""

            for page in pdf.pages:
                # x_tolerance=1 is important: some PDF exporters (Google Pay's
                # statement export is a known example) place characters close
                # enough together that pdfplumber's default tolerance merges
                # words together ("Paidto" instead of "Paid to").
                full_text += (page.extract_text(x_tolerance=1) or "") + "\n"
                for table in page.extract_tables():
                    transactions.extend(parse_statement_table(table))

            # No ruled table found -- try the UPI-app text-line pattern instead.
            if not transactions:
                transactions = parse_upi_statement_text(full_text)

            if not transactions:
                return jsonify({
                    "transactions": [],
                    "insights": None,
                    "warning": (
                        "Couldn't find any transactions in this PDF. It may be a "
                        "scanned image, or use a layout this parser doesn't "
                        "recognize yet."
                    ),
                })

            insights = build_statement_insights(transactions)
            return jsonify({
                "transactions": transactions,
                "insights": insights,
                "warning": None,
            })
    except Exception as exc:
        return jsonify({"error": f"Couldn't read this PDF: {exc}"}), 400


if __name__ == "__main__":
    if not DATABASE.exists():
        init_db()
        print(f"Initialized database at {DATABASE}")
    app.run(debug=True)