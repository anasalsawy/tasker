// Packaged builds ship without .env (it is gitignored), so REACT_APP_* can be
// undefined at build time. Fall back to the deployed Railway backend instead
// of baking "undefined://undefined" into the bundle. Dev keeps localhost via .env.
const PRODUCTION_DNS = 'dl-companion-production.up.railway.app';
const PROTOCOL = process.env.REACT_APP_PROTOCOL || 'https';
const DNS = process.env.REACT_APP_DNS || PRODUCTION_DNS;
const WEBSOCKET_PROTOCOL =
  process.env.REACT_APP_WEBSOCKET_PROTOCOL || (PROTOCOL === 'https' ? 'wss' : 'ws');

const SERVER_DNS = PROTOCOL + '://' + DNS;
const WEBSOCKET_DNS = WEBSOCKET_PROTOCOL + '://' + DNS;

const constants = {
  SERVER_URL: SERVER_DNS,
  BASE_URL: SERVER_DNS + '/apps',
  WEBSOCKET_URL: WEBSOCKET_DNS + '/apps',
  API_KEY: process.env.REACT_APP_API_KEY,
  APP_NAME: 'Hands',
  // Identifier/path unchanged by design; user-facing wordmark is "Hands".
  TASKER_LINK: 'https://github.com/anasalsawy/tasker',
  GENERAL_ERROR: 'Something wrong happened, please try again.',
  status: {
    INTERNAL_SERVER_ERROR: 500,
    UNAUTHORIZED: 401,
    FORBIDDEN: 403,
    BAD_REQUEST: 400
  }
};

export default constants;
