// Everything here runs purely in the browser. No fetch(), no backend calls --
// this satisfies the "client-side only" requirement for bill splitting.

const billTotalField = document.getElementById("bill-total");
const peopleList = document.getElementById("people-list");
const addPersonBtn = document.getElementById("add-person-btn");
const splitBtn = document.getElementById("split-btn");
const resultsBox = document.getElementById("split-results");
const resultsList = document.getElementById("split-results-list");
const remainderNote = document.getElementById("split-remainder-note");

addPersonBtn.addEventListener("click", () => {
  const row = document.createElement("div");
  row.className = "person-row";
  const count = peopleList.querySelectorAll(".person-name").length + 1;
  row.innerHTML = `<input type="text" class="person-name" placeholder="Person ${count} name">`;
  peopleList.appendChild(row);
});

splitBtn.addEventListener("click", () => {
  const total = parseFloat(billTotalField.value);

  const names = Array.from(document.querySelectorAll(".person-name"))
    .map((input) => input.value.trim())
    .filter((name) => name.length > 0);

  resultsBox.classList.add("hidden");
  remainderNote.classList.add("hidden");

  if (!total || total <= 0) {
    alert("Please enter a valid total bill amount.");
    return;
  }
  if (names.length === 0) {
    alert("Please enter at least one person's name.");
    return;
  }

  const shares = splitEvenly(total, names.length);

  resultsList.innerHTML = "";
  names.forEach((name, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${escapeHtml(name)}</span><span>₹${shares[i].toFixed(2)}</span>`;
    resultsList.appendChild(li);
  });

  resultsBox.classList.remove("hidden");
});

/**
 * Splits `total` into `count` shares as evenly as possible.
 * Money can't always divide evenly (e.g. ₹100 / 3 = ₹33.33 recurring),
 * so we round each share to 2 decimals, then hand any leftover paise
 * (caused by rounding) to the first few people, one rupee-cent at a time,
 * so the shares always sum back up to exactly the original total.
 */
function splitEvenly(total, count) {
  const totalPaise = Math.round(total * 100); // work in integer paise to avoid float errors
  const basePaise = Math.floor(totalPaise / count);
  const remainderPaise = totalPaise - basePaise * count;

  const sharesPaise = new Array(count).fill(basePaise);
  for (let i = 0; i < remainderPaise; i++) {
    sharesPaise[i] += 1; // distribute the leftover 1-paise units
  }

  return sharesPaise.map((p) => p / 100);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
