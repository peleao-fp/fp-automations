const cheerio = require('cheerio');

function normalizeHeader(h) {
  return h.toLowerCase()
    .replace(/[\s\/]+/g, '_')
    .replace(/[^a-z0-9_]/g, '');
}

function collapseSpaces(s) {
  return (s || '').replace(/\s+/g, ' ').trim();
}

// Integer box qty; anything not a positive number → 0 (line is skipped)
function parseQty(val) {
  const n = parseFloat(String(val || '').replace(/[^\d.\-]/g, ''));
  return isNaN(n) ? 0 : n;
}

// Parse one suggestion table → lines with qty > 0
function parseOneTable($, tbl) {
  const lines   = [];
  const skipped = [];
  let headers = [];

  $(tbl).find('tr').each((_, tr) => {
    const cells = $(tr).find('th, td').map((_, td) => collapseSpaces($(td).text())).get();
    if (!cells.length) return;
    if (!headers.length) {
      headers = cells.map(normalizeHeader);
      return;
    }

    const row = {};
    headers.forEach((h, idx) => { row[h] = cells[idx] || ''; });

    const product = row.product;
    if (!product) return;

    const qty = parseQty(row.suggested_bx);
    if (qty <= 0) {
      skipped.push({ product, reason: `Suggested_BX = ${row.suggested_bx || 'empty'}` });
      return;
    }

    lines.push({
      product,
      qty_boxes: qty,
      type:      row.type   || '',
      source:    row.source || '',
    });
  });

  return { headers, lines, skipped };
}

// "OM MIAMI — suggested order (customer 1158) — 26 boxes"
function parseTitle(text) {
  const customer = text.match(/customer\s*#?\s*(\d+)/i);
  const boxes    = text.match(/(\d+)\s*boxes/i);
  return {
    customer_no:    customer ? parseInt(customer[1], 10) : null,
    expected_boxes: boxes    ? parseInt(boxes[1], 10)    : null,
  };
}

function parseFlowersEmail(subject, html) {
  const $ = cheerio.load(html || '');
  const lines   = [];
  const skipped = [];

  $('table').each((_, tbl) => {
    // Only innermost tables that carry the suggestion columns
    if ($(tbl).find('table').length) return;
    const r = parseOneTable($, tbl);
    if (!r.headers.includes('product') || !r.headers.includes('suggested_bx')) return;
    lines.push(...r.lines);
    skipped.push(...r.skipped);
  });

  const bodyText = collapseSpaces($('body').text() || $.root().text());
  const title    = parseTitle(bodyText);

  return {
    subject,
    customer_no:    title.customer_no,
    expected_boxes: title.expected_boxes,
    total_boxes:    lines.reduce((s, l) => s + l.qty_boxes, 0),
    lines,
    skipped,
  };
}

module.exports = { parseFlowersEmail, collapseSpaces };
