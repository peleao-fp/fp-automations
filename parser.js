const cheerio = require('cheerio');
const cfg     = require('./config');

function detectLocation(subject) {
  const upper = (subject || '').toUpperCase();
  for (const [loc, keywords] of Object.entries(cfg.LOCATION_KEYWORDS)) {
    if (keywords.some(kw => upper.includes(kw))) return loc;
  }
  return null;
}

function detectGrowerName(subject) {
  const m = (subject || '').match(/[-–]\s+(.+?)\s+SUGGESTED/i);
  if (m) return m[1].trim();
  return 'Unknown';
}

// "UN 616-24-07 GREEN..." → "UN616-24-07"
// "4042-06-13 / RBY905..." → "4042-06-13"
// "023886CRM CALLA..." → "023886CRM"
function extractCode(productStr) {
  const parts = (productStr || '').trim().split(/\s+/);
  if (!parts.length) return '';
  const first = parts[0];
  if (first.length <= 3 && /^[A-Za-z]+$/.test(first) && parts[1] && /\d/.test(parts[1])) {
    return first + parts[1];
  }
  return first;
}

// Strip $ signs and parse float: "$ 55.35" → 55.35
function parseNum(val) {
  if (!val && val !== 0) return 0;
  const cleaned = String(val).replace(/[$€£¥\s]/g, '').replace(',', '.').trim();
  const n = parseFloat(cleaned);
  return isNaN(n) ? 0 : n;
}

function getColValue(row, ...names) {
  for (const name of names) {
    const val = row[name];
    if (val !== undefined && val !== '') return val;
  }
  return '';
}

function normalizeHeader(h) {
  return h.toLowerCase()
    .replace(/[\s\/]+/g, '_')
    .replace(/[^a-z0-9_]/g, '');
}

function parseTable(html) {
  const $ = cheerio.load(html);
  const rows = [];
  let headers = [];

  let bestTable = null, bestCount = 0;
  $('table').each((_, tbl) => {
    const count = $(tbl).find('tr').length;
    if (count > bestCount) { bestCount = count; bestTable = tbl; }
  });
  if (!bestTable) return rows;

  $(bestTable).find('tr').each((i, tr) => {
    const cells = $(tr).find('th, td').map((_, td) => $(td).text().trim()).get();
    if (!cells.length) return;
    if (i === 0 || !headers.length) {
      headers = cells.map(normalizeHeader);
      return;
    }
    const row = {};
    headers.forEach((h, idx) => { row[h] = cells[idx] || ''; });
    rows.push(row);
  });

  return rows;
}

function parseEmail(subject, htmlBody) {
  const location   = detectLocation(subject);
  const growerName = detectGrowerName(subject);
  const rawRows    = parseTable(htmlBody);
  const lines      = [];

  for (const r of rawRows) {
    const productStr = getColValue(r, 'product', 'product_name', 'description', 'item');
    if (!productStr) continue;

    // Quantity
    const qtyRaw = getColValue(r, 'suggested_bx', 'suggested', 'qty', 'quantity', 'order', 'boxes');
    const qty    = parseNum(qtyRaw);

    // Price — strips $ automatically
    const priceRaw = getColValue(r, 'box_price', 'price', 'unit_price', 'bp', 'cost');
    const price    = parseNum(priceRaw);

    // Skip if no suggested quantity AND no max
    const max = parseNum(getColValue(r, 'max', 'maximum'));
    if (qty === 0 && max === 0) continue;

    const code = extractCode(productStr);
    if (!code) continue;

    lines.push({
      product_code: productStr.trim(),
      qty_boxes:    qty > 0 ? qty : 1,
      box_price:    price,
      source:       getColValue(r, 'source', 'type').trim(),
    });
  }

  return { location, grower_name: growerName, subject, lines };
}

module.exports = { detectLocation, parseTable, parseEmail, extractCode };
