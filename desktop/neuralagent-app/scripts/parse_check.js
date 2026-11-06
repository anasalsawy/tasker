/** Parse-check JSX/ESM sources with the app's own babel preset (no build). */
const path = require('path');
const fs = require('fs');
const babel = require(path.join(process.cwd(), 'node_modules', '@babel', 'core'));
const files = process.argv.slice(2);
let fail = 0;
for (const f of files) {
  try {
    babel.transformSync(fs.readFileSync(f, 'utf8'), {
      filename: f, presets: [require(path.join(process.cwd(), 'node_modules', 'babel-preset-react-app'))],
      babelrc: false, configFile: false,
    });
    console.log('PARSE OK: ' + f);
  } catch (e) {
    fail = 1;
    console.log('PARSE FAIL: ' + f + ' :: ' + e.message.split('\n')[0]);
  }
}
process.exit(fail);
