// ============================================================
// OM MIAMI — FLOWERS SUGGESTED
// Email "OM Miami - FLOWERS SUGGESTED" (Thursday) → 1 prebook for
// customer 1158, PICK - UP, delivery next Monday.
// UQs taken from existing 1158 prebooks in Flexymax (Sep/2026).
// ============================================================
module.exports = {
  NAME:           'OM Miami Flowers',
  LOCATION:       'MIA',
  TYPE:           'FLOWERS',
  CUSTOMER_NO:    1158,

  PREBOOK: {
    label:        'FULL POT - MIAMI-FLOWERS - 1158',
    customer_uq:  'EF8C1A9E',
    shipto_uq:    '902E3C20',   // FULL POT - MIAMI (only ship-to)
    carrier_uq:   'DNKT7342',   // PICK - UP
    carrier_name: 'PICK - UP',
    whouse_uq:    'BC0F7E5B',   // MIAMI - OM MIA
    terms_uq:     'C768DD5B',   // NET 45
  },

  // pb_date = next Monday; shipping_date = the day before (same as manual 1158 prebooks)
  DELIVERY_WEEKDAY:          1,   // 0=Sun, 1=Mon, ...
  SHIP_DAYS_BEFORE_DELIVERY: 1,
  TIMEZONE:                  'America/New_York',

  // How many search results to scan for the exact description
  PRODUCT_SEARCH_PAGE_SIZE:  50,
};
