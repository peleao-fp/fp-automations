// ============================================================
// EMAIL PARSER - extracts prebook data from suggestion emails
// ============================================================
const cheerio = require('cheerio');
const cfg     = require('./config');

// Detect location from email subject
function detectLocation(subject) {
  const upper = (subject || '').toUpperCase();
  for (const [loc, keywords] of Object.entries(cfg.LOCATION_KEYWORDS)) {
    if (keywords.some(kw => upper.includes(kw))) return loc;
  }
  return null;
}

// Detect grower name from email subject or body
// e.g. "NPL HardGoods - Plus One SUGGESTED" → "Plus One"
function detectGrowerName(subject, body) {
  const text = `${subject || ''} ${body || ''}`;
  // Common pattern: "- GrowerName SUGGESTED"
  const m = text.match(/[-–]\s+(.+?)\s+SUGGESTED/i);
  if (m) return m[1].trim();
  return 'Unknown';
}

// Parse HTML table → array of product rows
function parseTable(html) {
  const $ = cheerio.load(html);
  const rows = [];
  let headers = [];

  $('table').first().find('tr').each((i, tr) => {
    const cells = $(tr).find('th, td').map((_, td) => $(td).text().trim()).get();
    if (cells.length === 0) return;

    if (i === 0 || headers.length === 0) {
      // Header row
      headers = cells.map(h => h.toLowerCase().replace(/\s+/g, '_'));
      return;
    }

    const row = {};
    headers.forEach((h, idx) => { row[h] = cells[idx] || ''; });
    rows.push(row);
  });

  return rows;
}

// Parse a single email into structured prebook data
function parseEmail(subject, htmlBody) {
  const location   = detectLocation(subject);
  const growerName = detectGrowerName(subject, htmlBody);

  if (!location) {
    console.warn(`⚠️  Could not detect location from subject: "${subject}"`);
  }

  const rawRows = parseTable(htmlBody);

  const lines = rawRows
    .filter(r => {
      const qty = parseInt(r.suggested_bx || r.suggested || '0', 10);
      return qty > 0 && r.product;
    })
    .map(r => ({
      product_code: (r.product || '').trim(),
      qty_boxes:    parseInt(r.suggested_bx || r.suggested || '0', 10),
      box_price:    parseFloat((r.box_price || '0').replace(',', '.')),
      unit_price:   parseFloat((r.unit_price || '0').replace(',', '.') || '0'),
      source:       (r.source || '').trim(),
    }));

  return {
    location,
    grower_name: growerName,
    subject,
    lines,
  };
}

module.exports = { detectLocation, parseTable, parseEmail };
