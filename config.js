// ============================================================
// FLEXYMAX UQ MAPPINGS - Full Pot Prebook Automation
// ============================================================

module.exports = {

  // Flexymax API
  FLEXYMAX_BASE_URL: 'https://app.flexymax.com/api/v1/actions/execute',
  ANONYMOUS_USER_ID: 'ba68aa44-49dc-4dbf-8145-864bb24cd52d',

  // Action IDs
  ACTIONS: {
    SEARCH_PRODUCT:       '659f60bcb185274a675b81e0',
    CREATE_PREBOOK:       '659f60bcb185274a675b81fc',
    INSERT_LINE:          '659f60bcb185274a675b81f0',
    READ_HEADER:          '659f60bcb185274a675b81e1',
    READ_LINES:           '659f60bcb185274a675b81d8',
    GET_CARRIERS:         '659f60bcb185274a675b8209',
    GET_SHIP_ADDRESS:     '659f60bcb185274a675b820a',
    GET_CUSTOMER_TERMS:   '659f60bcb185274a675b81fe',
    DATE_TO_JULIAN:       '659f60bcb185274a675b8201',
    GET_USER_WAREHOUSES:  '659f60bcb185274a675b8202',
  },

  // Salesman (Pedro)
  SALESMAN_UQ: 'C9145113',

  // Warehouse: Miami Pre Orders
  WAREHOUSE_UQ: '2O9R6656',

  // Terms: NET 45 (same for all customers)
  TERMS_UQ: 'C768DD5B',

  // Shipping: prebook_date + 7 days
  SHIPPING_DAYS_AHEAD: 7,

  // Customer mapping by location (always UNITS)
  CUSTOMERS: {
    FLL: {
      label:        'Full Pot FLL - Unit HardGoods',
      customer_uq:  '8D53FD6B',
      shipto_uq:    '37BC4BF7',
    },
    WPB: {
      label:        'WPB HardGoods Units',
      customer_uq:  '8D96D3B2',
      shipto_uq:    '6C230940',
    },
    NPL: {
      label:        'Naples HardGoods Units',
      customer_uq:  '9A8B3BB3',
      shipto_uq:    '36357CDB',
    },
    ORL: {
      label:        'HG Units MCO (Orlando)',
      customer_uq:  'BC0FED72',
      shipto_uq:    'D3101F70',
    },
  },

  // Keywords to detect location in email subject
  LOCATION_KEYWORDS: {
    FLL: ['FLL', 'FORT LAUDERDALE', 'LAUDERDALE'],
    WPB: ['WPB', 'WEST PALM', 'PALM BEACH'],
    NPL: ['NPL', 'NAPLES', 'NAP'],
    ORL: ['ORL', 'ORLANDO', 'MCO'],
  },

};
