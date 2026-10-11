const $ = (id) => document.getElementById(id);
let current = null;

async function post(path, body) {
  const r = await fetch(path, {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

$("reviewBtn").onclick = async () => {
  const comment = $("comment").value;
  $("status").textContent = "reviewing…";
  try {
    current = await post("/api/review", {comment});
    render(current);
    $("status").textContent = "";
  } catch (e) { $("status").textContent = "error: " + e.message; }
};

function render(rec) {
  $("result").hidden = false;
  const a = rec.assessment;
  $("cls").textContent = a.classification;
  $("cls").className = a.classification;
  $("rationale").textContent = a.rationale;
  $("flags").innerHTML = (a.flags || []).map(
    f => `<span class="flag">${f}</span>`).join(" ") +
    (a.unverified_citations || []).map(
    c => `<span class="flag warn">unverified citation: ${c}</span>`).join(" ");
  $("evidence").innerHTML = (a.evidence || []).map(c =>
    `<li><strong>${c.id}</strong> — ${c.statement}<br><em>${
      c.references.map(r => `[${r.type}] ${r.ref}`).join("; ")}</em></li>`
  ).join("") || "<li>None — answer: UNKNOWN.</li>";
  $("draft").textContent = rec.draft.draft;
  $("challengeForm").hidden = a.classification !== "TESTABLE";
  if (a.classification === "TESTABLE") {
    $("chgClaim").value = $("comment").value.slice(0, 160);
  }
}

$("approveBtn").onclick = async () => {
  if (!current) return;
  const note = prompt("Approval note (optional):", "") || "";
  current = await post("/api/approve",
    {review_id: current.review_id, decision: "approved", note});
  render(current);
  $("status").textContent = "approval recorded locally (not published)";
  refresh();
};

$("challengeBtn").onclick = () => {
  $("challengeForm").hidden = !$("challengeForm").hidden;
};

$("chgSave").onclick = async () => {
  const rec = await post("/api/challenge", {
    claim: $("chgClaim").value,
    proposed_falsifier: $("chgFalsifier").value,
    source_review_id: current && current.review_id});
  $("status").textContent = "challenge " + rec.challenge_id + " recorded";
  $("challengeForm").hidden = true;
  refresh();
};

async function refresh() {
  const r = await fetch("/api/records").then(x => x.json());
  $("records").innerHTML = r.records.map(d =>
    `<li><code>${d.review_id || d.challenge_id}</code> — ${
      d.assessment ? d.assessment.classification + " · " +
        (d.human_approval ? "approved" : "draft") : "challenge · " +
        d.test_status}</li>`).join("");
}

$("refreshBtn").onclick = refresh;

$("exportBtn").onclick = async () => {
  const r = await fetch("/api/export").then(x => x.json());
  $("exportOut").hidden = false;
  $("exportOut").textContent = JSON.stringify(r, null, 2);
};

refresh();
