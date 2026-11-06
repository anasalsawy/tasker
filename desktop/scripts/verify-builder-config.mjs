// Offline verification of electron-builder config for Hands.
// Checks every input the NSIS build needs and prints a PASS/FAIL report.
// Exit 1 if anything is missing (CI gate before running the real builder).
import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const root = path.resolve(process.cwd());
const problems = [];
const notes = [];
const ok = (m) => console.log('  PASS ' + m);
const bad = (m) => { problems.push(m); console.log('  FAIL ' + m); };

console.log('[check] electron-builder config for', root);

// 1. package.json
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
if (pkg.build) bad('package.json still has a "build" key; electron-builder.yml is authoritative');
else ok('package.json has no inline "build" block (electron-builder.yml wins)');
if (!/^\d+\.\d+\.\d+/.test(pkg.version)) bad(`invalid semver version: ${pkg.version}`);
else ok(`version ${pkg.version}`);
if (!pkg.dependencies?.['electron-updater']) bad('electron-updater missing from dependencies');
else ok('electron-updater dependency present');
if (!pkg.scripts?.['dist:win']) bad('dist:win script missing');
else ok('dist:win script present');

// 2. electron-builder.yml
const ymlPath = path.join(root, 'electron-builder.yml');
if (!fs.existsSync(ymlPath)) { bad('electron-builder.yml missing'); report(); }
const yml = fs.readFileSync(ymlPath, 'utf8');
const wants = [
  ['appId: com.hands.desktop', 'appId com.hands.desktop'],
  ['productName: Hands', 'productName Hands'],
  ['provider: github', 'publish provider github'],
  ['owner: anasalsawy', 'publish owner anasalsawy'],
  ['repo: tasker', 'publish repo tasker'],
  ['target: nsis', 'nsis target'],
];
for (const [needle, label] of wants) {
  if (yml.includes(needle)) ok(label);
  else bad(`${label} not found in electron-builder.yml (looked for "${needle}")`);
}

// 3. buildResources / icon
const icon = path.resolve(root, 'assets/icon.ico');
const png = path.resolve(root, 'assets/icon.png');
if (fs.existsSync(icon)) ok(`assets/icon.ico ${fs.statSync(icon).size} bytes`);
else bad('assets/icon.ico missing - NSIS will fail: run powershell desktop/assets/make-ico.ps1');
if (fs.existsSync(png)) ok(`assets/icon.png ${fs.statSync(png).size} bytes`);
else bad('assets/icon.png missing');

// 4. app payload
const buildDir = path.resolve(root, 'neuralagent-app/build');
fs.existsSync(path.join(buildDir, 'index.html'))
  ? ok('neuralagent-app/build/index.html exists')
  : bad('neuralagent-app/build/index.html missing - run npm run react-build first');
fs.existsSync(path.resolve(root, 'main.js')) ? ok('main.js exists') : bad('main.js missing');
fs.existsSync(path.resolve(root, 'electron/preload.js')) ? ok('electron/preload.js exists') : bad('preload missing');

// 5. extraResources - these are gitignored, built by PyInstaller
for (const exe of ['agent.exe', 'suggestor.exe']) {
  const p = path.resolve(root, 'agent_build', exe);
  if (fs.existsSync(p)) ok(`agent_build/${exe} ${fs.statSync(p).size} bytes`);
  else bad(`agent_build/${exe} missing - extraResources will fail. Run npm run build:agent / build:suggestor`);
}

// 6. local-only builder sanity (no network, no NSIS): can we load app-builder-lib?
try {
  const v = require('app-builder-lib/package.json').version;
  notes.push(`app-builder-lib ${v} loadable`);
} catch (e) {
  try {
    const p = JSON.parse(fs.readFileSync(path.resolve(root, 'node_modules/app-builder-lib/package.json'), 'utf8'));
    notes.push(`app-builder-lib ${p.version} present on disk`);
  } catch (e2) {
    bad('app-builder-lib not installed - run npm ci in desktop/');
  }
}

report();

function report() {
  console.log('\n[check] notes:');
  notes.forEach((n) => console.log('  - ' + n));
  console.log(`\n[check] ${problems.length} problem(s)`);
  if (problems.length) {
    problems.forEach((p, i) => console.log(`  ${i + 1}. ${p}`));
    process.exit(1);
  }
  console.log('[check] config OK (NSIS packaging itself must run on Windows w/ network)');
  process.exit(0);
}
