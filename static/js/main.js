// ---------------------------------------------------------------------------
// State + element references
// ---------------------------------------------------------------------------
let categoryChart = null; // holds the Chart.js instance so we can destroy/redraw it

const form = document.getElementById("expense-form");
const expenseIdField = document.getElementById("expense-id");
const amountField = document.getElementById("amount");
const categoryField = document.getElementById("category");
const dateField = document.getElementById("date");
const descriptionField = document.getElementById("description");
const submitBtn = document.getElementById("submit-btn");
const cancelEditBtn = document.getElementById("cancel-edit-btn");
const formError = document.getElementById("form-error");

const monthSelect = document.getElementById("month-select");
const totalAmountEl = document.getElementById("total-amount");
const tableBody = document.getElementById("expense-table-body");
const emptyState = document.getElementById("empty-state");

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
function currentMonthString() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

document.addEventListener("DOMContentLoaded", () => {
  dateField.value = new Date().toISOString().slice(0, 10); // default to today
  monthSelect.value = currentMonthString();

  loadExpenses();
  loadSummary(monthSelect.value);
});

monthSelect.addEventListener("change", () => loadSummary(monthSelect.value));

// ---------------------------------------------------------------------------
// Fetch + render expenses table
// ---------------------------------------------------------------------------
async function loadExpenses() {
  const res = await fetch("/api/expenses");
  const expenses = await res.json();
  renderTable(expenses);
}

function renderTable(expenses) {
  tableBody.innerHTML = "";

  if (expenses.length === 0) {
    emptyState.classList.remove("hidden");
    return;
  }
  emptyState.classList.add("hidden");

  for (const exp of expenses) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${exp.date}</td>
      <td>${escapeHtml(exp.category)}</td>
      <td>${escapeHtml(exp.description || "")}</td>
      <td>₹${exp.amount.toFixed(2)}</td>
      <td>
        <button class="edit-btn" data-id="${exp.id}">Edit</button>
        <button class="danger-btn" data-id="${exp.id}">Delete</button>
      </td>
    `;
    tableBody.appendChild(tr);
  }

  // Attach listeners after rows exist (event delegation would also work here)
  tableBody.querySelectorAll(".edit-btn").forEach((btn) => {
    btn.addEventListener("click", () => startEdit(btn.dataset.id, expenses));
  });
  tableBody.querySelectorAll(".danger-btn").forEach((btn) => {
    btn.addEventListener("click", () => deleteExpense(btn.dataset.id));
  });
}

// Basic escaping so a description like "<script>" can't break the page.
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Add / Edit form submission
// ---------------------------------------------------------------------------
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  formError.classList.add("hidden");

  const payload = {
    amount: parseFloat(amountField.value),
    category: categoryField.value,
    date: dateField.value,
    description: descriptionField.value,
  };

  const editingId = expenseIdField.value;
  const url = editingId ? `/api/expenses/${editingId}` : "/api/expenses";
  const method = editingId ? "PUT" : "POST";

  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await res.json();

  if (!res.ok) {
    formError.textContent = data.error || "Something went wrong";
    formError.classList.remove("hidden");
    return;
  }

  resetForm();
  loadExpenses();
  loadSummary(monthSelect.value);
});

function startEdit(id, expenses) {
  const exp = expenses.find((e) => String(e.id) === String(id));
  if (!exp) return;

  expenseIdField.value = exp.id;
  amountField.value = exp.amount;
  categoryField.value = exp.category;
  dateField.value = exp.date;
  descriptionField.value = exp.description || "";

  submitBtn.textContent = "Update Expense";
  cancelEditBtn.classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

cancelEditBtn.addEventListener("click", resetForm);

function resetForm() {
  form.reset();
  expenseIdField.value = "";
  dateField.value = new Date().toISOString().slice(0, 10);
  submitBtn.textContent = "Add Expense";
  cancelEditBtn.classList.add("hidden");
}

async function deleteExpense(id) {
  if (!confirm("Delete this expense?")) return;

  await fetch(`/api/expenses/${id}`, { method: "DELETE" });
  loadExpenses();
  loadSummary(monthSelect.value);
}

// ---------------------------------------------------------------------------
// Summary + Chart.js
// ---------------------------------------------------------------------------
async function loadSummary(month) {
  const res = await fetch(`/api/summary?month=${month}`);
  const summary = await res.json();

  totalAmountEl.textContent = `₹${summary.total.toFixed(2)}`;
  renderChart(summary.by_category);
}

function renderChart(byCategory) {
  const ctx = document.getElementById("category-chart");

  const labels = byCategory.map((c) => c.category);
  const totals = byCategory.map((c) => c.total);

  // Destroy the previous chart instance before drawing a new one,
  // otherwise Chart.js stacks canvases on top of each other.
  if (categoryChart) {
    categoryChart.destroy();
  }

  categoryChart = new Chart(ctx, {
    type: "pie",
    data: {
      labels: labels.length ? labels : ["No data"],
      datasets: [{
        data: totals.length ? totals : [1],
        backgroundColor: [
          "#2f6f4f", "#7fb069", "#d4a24c", "#c0392b",
          "#4a6fa5", "#8e6c88", "#5c8374",
        ],
      }],
    },
    options: {
      plugins: {
        legend: { position: "bottom" },
      },
    },
  });
}
