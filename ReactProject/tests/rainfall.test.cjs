const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const ts = require('typescript');
const vm = require('node:vm');
function load(path, globals = {}) {
  const source = readFileSync(require.resolve(path), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const sandbox = { exports: {}, ...globals };
  vm.runInNewContext(compiled, sandbox);
  return sandbox.exports;
}
const { parseRainfallText, rainfallStats } = load('../src/utils/rainfall.ts');

test('CSV and spreadsheet paste preserve every interval including dry periods', () => {
  assert.deepEqual(
    Array.from(
      parseRainfallText('\uFEFFoffset_seconds,rainfall_mm\r\n0,0\r\n300,1.5\r\n600,0', 300),
    ),
    [0, 1.5, 0],
  );
  assert.deepEqual(Array.from(parseRainfallText('0\t0\n300\t1.5\n600\t0', 300)), [0, 1.5, 0]);
  assert.deepEqual(Array.from(parseRainfallText('rainfall_mm\n0\n1.5\n0', 300)), [0, 1.5, 0]);
  const stats = rainfallStats([0, 1.5, 0], 300);
  assert.equal(stats.total, 1.5);
  assert.equal(stats.peak, 18);
  assert.equal(stats.duration, 900);
});

test('invalid numbers, duplicate times and missing intervals report row numbers', () => {
  for (const text of [
    '0,1\n600,2',
    '0,1\n0,2',
    '0,1\n300,',
    '1\nNaN',
    '1\n-1',
    '1\nInfinity',
    '1\ntrue',
  ])
    assert.throws(() => parseRainfallText(text, 300), /第 2 行/);
  assert.throws(() => parseRainfallText('', 300), /请粘贴/);
});

test('workspace migration retains the active legacy real version and map settings', () => {
  let persisted = JSON.stringify({
    selectedModelId: 'jj',
    rainfallModes: { jj: 'real' },
    selectedVersionsByInput: { 'jj:design': 'v1', 'jj:real': 'v4' },
    activeResultsByInput: { 'jj:real': 'v4' },
    layerOrder: ['nodes'],
    layerVisibility: { nodes: false },
  });
  const workspace = load('../src/utils/workspaceState.ts', {
    window: {
      localStorage: {
        getItem: () => persisted,
        setItem: (_, value) => {
          persisted = value;
        },
      },
    },
  });
  const state = workspace.loadWorkspaceState();
  assert.equal(state.schemaVersion, 2);
  assert.equal(state.selectedVersionsByModel.jj, 'v4');
  assert.equal(state.activeResultsByModel.jj, 'v4');
  assert.equal(state.layerVisibility.nodes, false);
  workspace.saveWorkspaceState({ selectedVersionsByModel: { jj: 'v5' } });
  assert.equal(workspace.loadWorkspaceState().selectedVersionsByModel.jj, 'v5');
  assert.equal(JSON.parse(persisted).rainfallModes, undefined);
});
