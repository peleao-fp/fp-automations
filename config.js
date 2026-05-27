module.exports = {
  FLEXYMAX_BASE_URL: 'https://app.flexymax.com/api/v1/actions/execute',
  ANONYMOUS_USER_ID: 'ba68aa44-49dc-4dbf-8145-864bb24cd52d',
  ACTIONS: {
    SEARCH_PRODUCT:   '659f60bcb185274a675b81e0',
    CREATE_PREBOOK:   '659f60bcb185274a675b81fc',
    INSERT_LINE:      '659f60bcb185274a675b81f0',
    READ_HEADER:      '659f60bcb185274a675b81e1',
    GET_CARRIERS:     '659f60bcb185274a675b8209',
    GET_SHIP_ADDRESS: '659f60bcb185274a675b820a',
    DATE_TO_JULIAN:   '659f60bcb185274a675b8201',
  },
  SALESMAN_UQ:         'C9145113',
  WAREHOUSE_UQ:        '2O9R6656',
  TERMS_UQ:            'C768DD5B',
  SHIPPING_DAYS_AHEAD: 7,
  CUSTOMERS: {
    FLL: { label: 'Full Pot FLL Units',     customer_uq: '8D53FD6B', shipto_uq: '37BC4BF7' },
    WPB: { label: 'WPB HardGoods Units',    customer_uq: '8D96D3B2', shipto_uq: '6C230940' },
    NPL: { label: 'Naples HardGoods Units', customer_uq: '9A8B3BB3', shipto_uq: '36357CDB' },
    ORL: { label: 'HG Units MCO Orlando',   customer_uq: 'BC0FED72', shipto_uq: 'D3101F70' },
  },
  LOCATION_KEYWORDS: {
    FLL: ['FLL', 'FORT LAUDERDALE', 'LAUDERDALE', 'PMP', 'POMPANO'],
    WPB: ['WPB', 'WEST PALM', 'PALM BEACH'],
    NPL: ['NPL', 'NAPLES', 'NAP'],
    ORL: ['ORL', 'ORLANDO', 'MCO'],
  },
};
