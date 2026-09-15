const SERVER_DNS = process.env.REACT_APP_PROTOCOL + '://' + process.env.REACT_APP_DNS;
const WEBSOCKET_DNS = process.env.REACT_APP_WEBSOCKET_PROTOCOL + '://' + process.env.REACT_APP_DNS;

const constants = {
  BASE_URL: SERVER_DNS + '/apps',
  WEBSOCKET_URL: WEBSOCKET_DNS + '/apps',
  API_KEY: process.env.REACT_APP_API_KEY,
  APP_NAME: 'NeuralAgent',
  NEURALAGENT_LINK: 'https://www.getneuralagent.com',
  GENERAL_ERROR: 'Something wrong happened, please try again.',
  status: {
    INTERNAL_SERVER_ERROR: 500,
    UNAUTHORIZED: 401,
    FORBIDDEN: 403,
    BAD_REQUEST: 400
  }
};

export default constants;