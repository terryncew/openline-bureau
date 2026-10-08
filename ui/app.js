'use strict';
const content = document.querySelector('#content');
const notice = document.querySelector('#notice');
const detail = document.querySelector('#detail');

// Use textContent for all imported evidence, including advertised profiles.
function element(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (cls) node.className = cls;
  return node;
}
async function get(path) {
  const response = await fetch(path);
  if (!response.ok) throw Error(`${path}: ${response.status}`);
  return response.json();
}
async function receipt(id) {
  detail.textContent = JSON.stringify(await get('/api/receipt/' + encodeURIComponent(id)), null, 2);
}
function showError(error) { notice.textContent = error.message; }
function links(ids, root) {
  for (const id of ids) {
    const button = element('button', id, 'receipt');
    button.onclick = () => receipt(id).catch(showError);
    root.append(button);
  }
}
function metric(list, label, value, ids) {
  list.append(element('dt', label));
  const description = element('dd', value === null ? 'NOT MEASURABLE' : value);
  if (ids.length) {
    const button = element('button', 'Inspect supporting receipts');
    button.onclick = () => { detail.replaceChildren(); links(ids, detail); };
    description.append(element('br'), button);
  }
  list.append(description);
}
async function workers() {
  const data = await get('/api/workers');
  notice.textContent = data.warning;
  content.replaceChildren();
  const cards = element('div', undefined, 'cards');
  content.append(cards);
  for (const row of data.workers) {
    const card = element('article', undefined, 'card');
    cards.append(card);
    card.append(element('h2', row.profile.seller_name),
      element('p', `${row.profile.capability} · ${row.profile.price} SIM_USD offered (self-reported profile)`),
      element('p', row.ranking_status, 'unknown'));
    const list = element('dl');
    card.append(list);
    metric(list, 'Comparable buyer-verified jobs', row.comparable_verified_jobs, row.receipt_ids);
    metric(list, 'Buyer-verified accepted results', row.accepted, row.accepted_receipt_ids);
    metric(list, 'Buyer-verified rejected results (observed)', row.rejected, row.rejected_receipt_ids);
    metric(list, 'Accepted fraction of observed verdicts', row.accepted_fraction,
      row.accepted_receipt_ids.concat(row.rejected_receipt_ids));
    metric(list, 'Observed simulated settlement cost', row.observed_simulated_cost, row.cost_receipt_ids);
    metric(list, 'Accepted results per settled SIM_USD', row.accepted_per_simulated_unit,
      row.accepted_receipt_ids.concat(row.cost_receipt_ids));
    metric(list, 'All attempts / unobserved failures', null, []);
    card.append(element('p', row.denominator), element('p', row.cost_definition),
      element('p', row.authorization_standing, 'unknown'));
    if (row.unresolved_jobs.length) {
      card.append(element('p', 'Unresolved selected jobs: ' + row.unresolved_jobs.join(', '), 'unknown'));
    }
    const states = element('details');
    states.append(element('summary', 'Work and settlement evidence'));
    for (const job of row.job_states) {
      states.append(element('p', `${job.job_id}: ${job.outcome} · ${job.settlement}`));
    }
    card.append(states);
    const select = element('button', 'Review this worker in Wallet');
    select.onclick = () => {
      detail.textContent = `Worker ${row.worker_id}\nOffer ${row.profile.offer_id}\n` +
        'Use the local buyer CLI to prepare the exact input, review scope, maximum budget and expiry, then approve it. ' +
        'The Bureau browser is read-only and cannot grant authority.\n' +
        'See BUREAU_ALLOCATION_001.md for the complete walkthrough.';
    };
    card.append(select);
  }
  if (!data.workers.length) {
    content.append(element('p', 'No selected Exchange evidence loaded. Run the allocation walkthrough; missing history does not imply untrustworthiness.'));
  }
}
async function view(name) {
  if (name === 'workers') return workers();
  const data = await get('/api/' + name);
  notice.textContent = 'Existing Bureau views over the same receipt ledger.';
  content.replaceChildren();
  if (name === 'ledger') {
    const table = element('table');
    content.append(table);
    for (const record of data.records) {
      const row = element('tr');
      row.append(element('td', record.timestamp || 'UNKNOWN'), element('td', record.actor || 'UNKNOWN'),
        element('td', record.event_type || 'UNKNOWN'));
      const cell = element('td');
      links([record.receipt_id], cell);
      row.append(cell);
      table.append(row);
    }
  } else {
    content.append(element('pre', JSON.stringify(data, null, 2)));
  }
}
for (const button of document.querySelectorAll('[data-view]')) {
  button.onclick = () => view(button.dataset.view).catch(showError);
}
workers().catch(showError);
