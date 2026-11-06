try {
  const H = require('../src/state/handsMachine.js');
  console.log('REQUIRE OK keys=' + Object.keys(H).length);
  let s = H.initialState();
  s = H.reduce(s, { kind: 'user_text', text: 'hi' });
  console.