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
  const m = (subject || '').match(/[-–]\s+(.+?)\s+SUGGESTED/i);
  if (m) return m[1].trim();
  return null;
}

// Check if a text matches a grower in the GROWER_MAP
function matchGrowerFromText(text) {
  if (!text || text.length < 2 || text.length > 80) return null;
  const upper = text.trim().toUpperCase();
  const entry = cfg.GROWER_MAP.find(g =>
    g.match.some(m => upper.includes(m.toUpperCase()))
  );
  return entry ? text.trim() : null;
}

function extractCode(s) {
  const parts = (s||'').trim().split(/\s+/);
  if (!parts.length) return '';
  const first = parts[0];
  if (first.length <= 3 && /^[A-Za-z]+$/.test(first) && parts[1] && /\d/.test(parts[1])) {
    return first + parts[1];
  }
  if (/\d/.test(first)) return first;
  return (s||'').trim();
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
    if (!headers.some(h => h === 'product' || h === 'product_name')) return;

    const row = {};
    headers.forEach((h, idx) => { row[h] = cells[idx] || ''; });

    const productStr = getColValue(row, 'product', 'product_name', 'description', 'item');
    if (!productStr) return;

    const qty     = parseNum(getColValue(row, 'suggested_bx', 'suggested', 'qty', 'quantity', 'order', 'boxes'));
    const price   = parseNum(getColValue(row, 'box_price', 'price', 'bp', 'cost'));
    const uprice  = parseNum(getColValue(row, 'unit_price', 'unit_cost', 'price_unit', 'unitprice'));
    const max     = parseNum(getColValue(row, 'max', 'maximum'));
    const uxb     = parseNum(getColValue(row, 'units_x_box', 'units_x_case', 'units_per_box'));

    if (qty === 0 && max === 0) return;
    const code = extractCode(productStr);
    if (!code) return;

    lines.push({
      product_code: productStr.trim(),
      qty_boxes:    qty > 0 ? qty : 1,
      box_price:    price,
      unit_price:   uprice,
      units_x_box:  uxb,
      source:       getColValue(row, 'source', 'type').trim(),
      grower_name:  null, // filled in by parseAllTables
    });
  });

  return lines;
}

// Walk HTML in document order, tracking grower section headers
function parseAllTables(html) {
  const $ = cheerio.load(html);
  const allLines = [];
  let currentGrowerName = null;

  function walk(el) {
    const tag = $(el).prop('tagName')?.toLowerCase();

    if (tag === 'table') {
      const lines = parseOneTable($, el);
      lines.forEach(line => { line.grower_name = currentGrowerName; });
      allLines.push(...lines);
      return; // don't recurse into tables
    }

    // Extract text of this element (excluding nested tables)
    const directText = $(el).clone().find('table').remove().end().text().trim();

    // Check if this element is a potential grower header
    if (directText && directText.length >= 2 && directText.length <= 80) {
      const isHeader =
        ['b', 'strong', 'h1', 'h2', 'h3', 'h4'].includes(tag) ||
        $(el).children('b, strong').text().trim() === directText ||
        $(el).find('> b, > strong').length > 0;

      if (isHeader) {
        const matched = matchGrowerFromText(directText);
        if (matched) currentGrowerName = matched;
      }
    }

    // Recurse into children
    $(el).children().each((_, child) => walk(child));
  }

  $('body').children().each((_, el) => walk(el));

  return allLines;
}

function parseEmail(subject, htmlBody) {
  const location        = detectLocation(subject);
  const subjectGrower   = detectGrowerName(subject);
  const lines           = parseAllTables(htmlBody);

  // If no per-section growers found, fall back to subject grower for all lines
  const hasPerLineGrowers = lines.some(l => l.grower_name);
  if (!hasPerLineGrowers && subjectGrower) {
    lines.forEach(l => { l.grower_name = subjectGrower; });
  }

  return {
    location,
    grower_name: subjectGrower || 'Unknown',
    subject,
    lines,
  };
}

module.exports = { detectLocation, parseAllTables, parseEmail, extractCode, matchGrowerFromText };
