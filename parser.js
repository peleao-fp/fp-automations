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
  // "NPL HardGoods - Plus One SUGGESTED" → "Plus One"
  // "PMP WD Ceramic SUGGESTED" → "WD"
  const m = (subject || '').match(/[-–]\s+(.+?)\s+SUGGESTED/i);
  if (m) return m[1].trim();
  // Fallback: second word after location keyword
  const words = (subject || '').trim().split(/\s+/);
  if (words.length >= 2) return words[1];
  return 'Unknown';
}

function extractCode(productStr) {
  const parts = (productStr || '').trim().split(/\s+/);
  if (!parts.length) return '';
  const first = parts[0];
  // Short letter-only prefix + code → combine (e.g. "UN 616-24-07" → "UN616-24-07")
  if (first.length <= 3 && /^[A-Za-z]+$/.test(first) && parts[1] && /\d/.test(parts[1])) {
    return first + parts[1];
  }
  return first;
}

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

// Parse ONE table element → array of product lines
function parseOneTable($, tbl) {
  const lines = [];
  let headers = [];

  $(tbl).find('tr').each((i, tr) => {
    const cells = $(tr).find('th, td').map((_, td) => $(td).text().trim()).get();
    if (!cells.length) return;

    if (i === 0 || !headers.length) {
      headers = cells.map(normalizeHeader);
      return;
    }

    // Must have a product column
    if (!headers.some(h => h === 'product' || h === 'product_name')) return;

    const row = {};
    headers.forEach((h, idx) => { row[h] = cells[idx] || ''; });

    const productStr = getColValue(row, 'product', 'product_name', 'description', 'item');
    if (!productStr) return;

    const qtyRaw  = getColValue(row, 'suggested_bx', 'suggested', 'qty', 'quantity', 'order', 'boxes');
    const qty     = parseNum(qtyRaw);
    const priceRaw = getColValue(row, 'box_price', 'price', 'unit_price', 'bp', 'cost');
    const price   = parseNum(priceRaw);
    const max     = parseNum(getColValue(row, 'max', 'maximum'));

    // Skip rows with no suggested qty and no max
    if (qty === 0 && max === 0) return;

    const code = extractCode(productStr);
    if (!code) return;

    lines.push({
      product_code: productStr.trim(),
      qty_boxes:    qty > 0 ? qty : 1,
      box_price:    price,
      source:       getColValue(row, 'source', 'type').trim(),
    });
  });

  return lines;
}

// Parse ALL tables in the HTML and combine products
function parseAllTables(html) {
  const $ = cheerio.load(html);
  const allLines = [];

  $('table').each((_, tbl) => {
    const lines = parseOneTable($, tbl);
    if (lines.length > 0) {
      allLines.push(...lines);
    }
  });

  return allLines;
}

function parseEmail(subject, htmlBody) {
  const location   = detectLocation(subject);
  const growerName = detectGrowerName(subject);
  const lines      = parseAllTables(htmlBody);

  return { location, grower_name: growerName, subject, lines };
}

module.exports = { detectLocation, parseAllTables, parseEmail, extractCode };
