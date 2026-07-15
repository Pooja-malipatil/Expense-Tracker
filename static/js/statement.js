// ---------------------------------------------------------------------------
// Element references
// ---------------------------------------------------------------------------
const statementInput = document.getElementById("statement-input");
const statementUploadBtn = document.getElementById("statement-upload-btn");
const statementStatus = document.getElementById("statement-status");
const insightsSection = document.getElementById("insights-section");

const statTotalSent = document.getElementById("stat-total-sent");
const statTotalReceived = document.getElementById("stat-total-received");
const statNet = document.getElementById("stat-net");
const statCount = document.getElementById("stat-count");
const biggestExpenseText = document.getElementById("biggest-expense-text");

const frequencyTableBody = document.getElementById("frequency-table-body");
const frequencyEmpty = document.getElementById("frequency-empty");

const transactionsTableBody = document.getElementById("transactions-table-body");
const selectAllBtn = document.getElementById("select-all-btn");
const deselectAllBtn = document.getElementById("deselect-all-btn");
const importSelectedBtn = document.getElementById("import-selected-btn");
const importStatus = document.getElementById("import-status");

let recipientsChart = null;
let allTransactions = [];

// ---------------------------------------------------------------------------
// Upload + analyze
// ---------------------------------------------------------------------------
statementUploadBtn.addEventListener("click", async () => {
  const file = statementInput.files[0];
  if (!file) {
    alert("Choose a PDF file first.");
    return;
  }

  statementStatus.textContent = "Analyzing statement...";
  statementStatus.classList.remove("hidden");
  insightsSection.classList.add("hidden");

  const formData = new FormData();
  formData.append("pdf", file);

  const res = await fetch("/api/statement/analyze", { method: "POST", body: formData });
  const data = await res.json();

  if (!res.ok) {
    statementStatus.textContent = data.error || "Failed to analyze this PDF.";
    return;
  }

  if (!data.transactions || data.transactions.length === 0) {
    statementStatus.textContent = data.warning || "No transactions found in this PDF.";
    return;
  }

  statementStatus.textContent = `Found ${data.transactions.length} transaction(s).`;
  allTransactions = data.transactions;

  renderInsights(data.insights);
  renderTransactionsTable(allTransactions);
  insightsSection.classList.remove("hidden");
});

// ---------------------------------------------------------------------------
// Insights rendering
// ---------------------------------------------------------------------------
function renderInsights(insights) {
  statTotalSent.textContent = `₹${insights.total_sent.toFixed(2)}`;
  statTotalReceived.textContent = `₹${insights.total_received.toFixed(2)}`;
  statNet.textContent = `₹${insights.net.toFixed(2)}`;
  statCount.textContent = insights.transaction_count;

  if (insights.biggest_expense) {
    const be = insights.biggest_expense;
    biggestExpenseText.textContent =
      `₹${be.amount.toFixed(2)} to "${be.description || "Unknown"}" on ${be.date}`;
  } else {
    biggestExpenseText.textContent = "No expenses found in this statement.";
  }

  renderRecipientsChart(insights.top_recipients_by_spend);
  renderFrequencyTable(insights.top_recipients_by_frequency);
}

function renderRecipientsChart(topRecipients) {
  const ctx = document.getElementById("recipients-chart");

  if (recipientsChart) {
    recipientsChart.destroy();
  }

  const labels = topRecipients.length
    ? topRecipients.map((r) => r.name || "Unknown")
    : ["No data"];
  const totals = topRecipients.length ? topRecipients.map((r) => r.total) : [0];

  recipientsChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Amount Sent (₹)",
        data: totals,
        backgroundColor: "#2f6f4f",
      }],
    },
    options: {
      indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: { x: { beginAtZero: true } },
    },
  });
}

function renderFrequencyTable(topByFrequency) {
  frequencyTableBody.innerHTML = "";

  if (!topByFrequency || topByFrequency.length === 0) {
    frequencyEmpty.classList.remove("hidden");
    return;
  }
  frequencyEmpty.classList.add("hidden");

  for (const r of topByFrequency) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(r.name || "Unknown")}</td>
      <td>${r.count}</td>
      <td>₹${r.total.toFixed(2)}</td>
    `;
    frequencyTableBody.appendChild(tr);
  }
}

// ---------------------------------------------------------------------------
// Transactions table (with import selection)
// ---------------------------------------------------------------------------
function renderTransactionsTable(transactions) {
  transactionsTableBody.innerHTML = "";

  transactions.forEach((t, i) => {
    const tr = document.createElement("tr");
    const isSent = t.direction === "sent";
    tr.innerHTML = `
      <td><input type="checkbox" class="txn-check" data-index="${i}" ${isSent ? "checked" : ""}></td>
      <td>${t.date}</td>
      <td>${escapeHtml(t.description || "")}</td>
      <td><span class="direction-tag ${t.direction}">${isSent ? "Sent" : "Received"}</span></td>
      <td>
        <select class="txn-category" data-index="${i}">
          ${["Food","Travel","Utilities","Entertainment","Shopping","Rent","Other"].map(c =>
            `<option ${c === t.category ? "selected" : ""}>${c}</option>`).join("")}
        </select>
      </td>
      <td>₹${t.amount.toFixed(2)}</td>
    `;
    transactionsTableBody.appendChild(tr);
  });
}

selectAllBtn.addEventListener("click", () => {
  document.querySelectorAll(".txn-check").forEach((cb) => {
    const i = cb.dataset.index;
    if (allTransactions[i].direction === "sent") cb.checked = true;
  });
});

deselectAllBtn.addEventListener("click", () => {
  document.querySelectorAll(".txn-check").forEach((cb) => (cb.checked = false));
});

// ---------------------------------------------------------------------------
// Import selected "sent" transactions into the expense tracker
// ---------------------------------------------------------------------------
importSelectedBtn.addEventListener("click", async () => {
  const checks = document.querySelectorAll(".txn-check");
  let added = 0, skipped = 0, failed = 0;

  for (const check of checks) {
    const i = check.dataset.index;
    const txn = allTransactions[i];

    if (!check.checked) continue;
    if (txn.direction !== "sent") { skipped++; continue; } // only expenses make sense to import

    const category = document.querySelector(`.txn-category[data-index="${i}"]`).value;
    const payload = {
      amount: txn.amount,
      category,
      date: txn.date,
      description: txn.description,
    };

    const res = await fetch("/api/expenses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) added++; else failed++;
  }

  importStatus.textContent =
    `Imported ${added} expense(s).` +
    (failed ? ` ${failed} failed and were skipped.` : "") +
    (skipped ? ` ${skipped} "received" row(s) were skipped (not expenses).` : "");
  importStatus.classList.remove("hidden");
});

// ---------------------------------------------------------------------------
// Shared helper
// ---------------------------------------------------------------------------
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}