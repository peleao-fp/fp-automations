// ============================================================
// Publishes the flowers run result for Power Automate:
//   results_<RUN_KEY>.json  → { subject, timestamp, summary_html, results: [...] }
//   open_prebooks.json      → appends the new prebook (so DELETE replies work)
//
// Usage: node flowers/report.js flowers-result.json
// Env:   GH_TOKEN, RESULTS_GIST_ID, RUN_KEY, SUBJECT, RECIPIENTS, GITHUB_RUN_URL
// ============================================================
const fs  = require('fs');
const cfg = require('./config');
const { readGistFile, writeGistFiles } = require('./gist');

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function buildSummaryHtml(r, runUrl) {
  const logs = runUrl ? `<p><small>Logs: <a href="${esc(runUrl)}">${esc(runUrl)}</a></small></p>` : '';

  if (!r.success) {
    return `<h3>❌ ${esc(cfg.NAME)} — prebook NOT created</h3>`
      + `<p><b>Error:</b> ${esc(r.error || 'Unknown error')}</p>` + logs;
  }

  const title = r.dry_run
    ? `🧪 ${esc(cfg.NAME)} — DRY RUN (nothing was created)`
    : `✅ ${esc(cfg.NAME)} — prebook ready to close`;

  let html = `<h3>${title}</h3>`;
  if (!r.dry_run) {
    html += `<p>✅ ${esc(r.location)} ${esc(r.type)}: Prebook #<b>${esc(r.pbook_no)}</b> — ${r.ok} products OK`
      + (r.fail ? ` ⚠️ ${r.fail} failed` : '') + '</p>';
  } else {
    html += `<p>${r.ok} products found in Flexymax</p>`;
  }

  const boxesOk = r.expected_boxes == null || r.expected_boxes === r.total_boxes;
  html += '<p>'
    + `<b>Customer:</b> ${esc(r.customer)}<br>`
    + `<b>Carrier:</b> ${esc(r.carrier)}<br>`
    + `<b>PB date (delivery):</b> ${esc(r.pb_date)} &nbsp;|&nbsp; <b>Shipping:</b> ${esc(r.shipping_date)}<br>`
    + `<b>Boxes in table:</b> ${esc(r.total_boxes)}`
    + (r.expected_boxes != null ? ` (email says ${esc(r.expected_boxes)})${boxesOk ? '' : ' ⚠️ mismatch'}` : '')
    + '</p>';

  if (r.failed_items?.length) {
    html += '<p style="color:#cc0000"><b>⚠️ Not added to the prebook — add manually:</b><br>'
      + r.failed_items.map(f => `• ${esc(f.product)} (${esc(f.qty_boxes)} bx): ${esc(f.reason)}`).join('<br>')
      + '</p>';
  }
  if (r.warnings?.length) {
    html += '<p style="color:#b36b00"><b>⚠️ Please check:</b><br>'
      + r.warnings.map(w => `• ${esc(w.product)}: ${esc(w.reason)}`).join('<br>')
      + '</p>';
  }
  if (r.skipped_items?.length) {
    html += '<p><small>Skipped (Suggested_BX 0): '
      + r.skipped_items.map(s => esc(s.product)).join(', ') + '</small></p>';
  }
  return html + logs;
}

async function main() {
  const file   = process.argv[2] || 'flowers-result.json';
  const gistId = process.env.RESULTS_GIST_ID;
  const runKey = process.env.RUN_KEY || 'default';

  let r;
  try { r = JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch (e) {
    r = { location: cfg.LOCATION, type: cfg.TYPE, success: false, pbook_no: 0, prebook_uq: '', ok: 0, fail: 0,
          error: `Automation crashed before producing a result (${e.message})`, failed_items: [] };
  }

  const subject = process.env.SUBJECT || r.subject || '';
  const summary_html = buildSummaryHtml(r, process.env.GITHUB_RUN_URL);

  // Same shape the hardgoods flow parses (pbook_no must be an integer)
  const results = [{
    location:     r.location,
    type:         r.type,
    success:      !!r.success,
    pbook_no:     Number(r.pbook_no) || 0,
    prebook_uq:   r.prebook_uq || '',
    ok:           r.ok || 0,
    fail:         r.fail || 0,
    error:        r.error || null,
    failed_items: r.failed_items || [],
  }];

  const payload = { subject, status: r.success ? 'done' : 'failed', timestamp: new Date().toISOString(), summary_html, results };

  if (!gistId) {
    console.log('RESULTS_GIST_ID not set — printing instead of publishing');
    console.log(JSON.stringify(payload, null, 2));
    return;
  }

  await writeGistFiles(gistId, { [`results_${runKey}.json`]: JSON.stringify(payload, null, 2) });
  console.log(`Saved results_${runKey}.json`);

  // Track real prebooks so "DELETE" replies can find them
  if (r.success && !r.dry_run && r.prebook_uq) {
    let open = [];
    try { open = JSON.parse(await readGistFile(gistId, 'open_prebooks.json') || '[]'); } catch (e) {}
    open.push({
      prebook_uq: r.prebook_uq,
      pbook_no:   Number(r.pbook_no) || 0,
      location:   r.location,
      type:       r.type,
      subject,
      recipients: process.env.RECIPIENTS || '',
      created_at: new Date().toISOString(),
    });
    await writeGistFiles(gistId, { 'open_prebooks.json': JSON.stringify(open, null, 2) });
    console.log(`Tracking updated — ${open.length} open prebooks`);
  }
}

if (require.main === module) main().catch(e => { console.error('Report error:', e.message); process.exit(1); });

module.exports = { buildSummaryHtml };
