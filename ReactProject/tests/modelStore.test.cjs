const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

// Exercise the real Zustand store with isolated API and local-storage adapters.
// No browser, database, MinIO, or additional test dependencies are required.
function fixture(persisted = {}) {
  let saved = structuredClone(persisted);
  const calls = { saves: [], runs: [] };
  const models = [
    {
      id: 'jj',
      name: 'JJ',
      rainfall_inputs: [
        { mode: 'design', baseline_version_id: 'jj-design' },
        { mode: 'real', baseline_version_id: 'jj-real' },
      ],
    },
    {
      id: 'lc',
      name: 'LC',
      rainfall_inputs: [{ mode: 'design', baseline_version_id: 'lc-design' }],
    },
  ];
  const versions = {
    jj: [
      { id: 'jj-real-tuned', rainfall_mode: 'real', version: 4 },
      { id: 'jj-design-tuned', rainfall_mode: 'design', version: 3 },
      { id: 'jj-real', rainfall_mode: 'real', version: 2 },
      // Legacy design versions need no rainfall metadata.
      { id: 'jj-design', version: 1 },
    ],
    lc: [{ id: 'lc-design', rainfall_mode: 'design', version: 1 }],
  };
  const api = {
    fetchModels: async () => models,
    fetchVersions: async (id) => versions[id],
    fetchSections: async () => [],
    fetchEditableParameters: async (id) => ({
      groups: [],
      simulation_options: { duration_seconds: id.includes('real') ? 172800 : 3600 },
      rainfall_options: {
        mode: id.includes('real') ? 'real' : 'design',
        read_only: id.includes('real'),
      },
    }),
    fetchModelResults: async (id) => versions[id].map((version) => ({ version_id: version.id })),
    runProjectVersion: async (id) => {
      calls.runs.push(id);
      return { model_version_id: id };
    },
    createAdjustedVersion: async (parent, changes, summary, simulation, rainfall) => {
      calls.saves.push({ parent, changes, simulation, rainfall });
      const version = { id: 'jj-real-new', version: 5, rainfall_mode: 'real' };
      versions.jj = [version, ...versions.jj];
      return { version };
    },
  };
  const workspace = {
    loadWorkspaceState: () => structuredClone(saved),
    saveWorkspaceState: (patch) => {
      saved = { ...saved, ...structuredClone(patch) };
    },
    clearWorkspaceState: () => {
      saved = {};
    },
  };
  const source = readFileSync(require.resolve('../src/stores/modelStore.ts'), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const sandbox = {
    exports: {},
    require: (name) =>
      name === '@/api/models' ? api : name === '@/utils/workspaceState' ? workspace : require(name),
  };
  vm.runInNewContext(compiled, sandbox);
  return { store: sandbox.exports.useModelStore, api, calls, saved: () => saved };
}

test('switching selects pre-existing full inputs and never saves a version', async () => {
  const { store, calls } = fixture();
  await store.getState().loadModels();
  assert.equal(store.getState().selectedVersionId, 'jj-design');
  await store.getState().selectRainfallInput('real');
  assert.equal(store.getState().selectedVersionId, 'jj-real');
  assert.equal(store.getState().rainfallOptions.read_only, true);
  assert.equal(store.getState().simulationOptions.duration_seconds, 172800);
  await store.getState().runSelectedVersion();
  assert.deepEqual(calls.runs, ['jj-real']);
  await store.getState().selectRainfallInput('design');
  assert.equal(store.getState().selectedVersionId, 'jj-design');
  assert.equal(store.getState().rainfallOptions.read_only, false);
  assert.equal(store.getState().allVersions.length, 4);
  assert.equal(calls.saves.length, 0);
});

test('versions and results are isolated and restored for each input', async () => {
  const { store } = fixture();
  await store.getState().loadModels();
  await store.getState().selectVersion('jj-design-tuned');
  store.getState().activateResultVersion('jj-design-tuned');
  await store.getState().selectRainfallInput('real');
  assert.ok(store.getState().versions.every((version) => version.rainfall_mode === 'real'));
  assert.ok(
    store.getState().availableResults.every((result) => result.version_id.includes('real')),
  );
  assert.equal(store.getState().activeResultVersionId, null);
  await store.getState().selectVersion('jj-real-tuned');
  store.getState().activateResultVersion('jj-real-tuned');
  // Attempting to select a version/result from another input cannot leak state.
  await store.getState().selectVersion('jj-design-tuned');
  store.getState().activateResultVersion('jj-design-tuned');
  assert.equal(store.getState().selectedVersionId, 'jj-real-tuned');
  assert.equal(store.getState().activeResultVersionId, 'jj-real-tuned');
  await store.getState().selectRainfallInput('design');
  assert.equal(store.getState().selectedVersionId, 'jj-design-tuned');
  assert.equal(store.getState().activeResultVersionId, 'jj-design-tuned');
  await store.getState().selectRainfallInput('real');
  assert.equal(store.getState().selectedVersionId, 'jj-real-tuned');
  assert.equal(store.getState().activeResultVersionId, 'jj-real-tuned');
});

test('refresh restores the research area, input, version, and result', async () => {
  const first = fixture();
  await first.store.getState().loadModels();
  await first.store.getState().selectRainfallInput('real');
  await first.store.getState().selectVersion('jj-real-tuned');
  first.store.getState().activateResultVersion('jj-real-tuned');
  const refreshed = fixture(first.saved());
  await refreshed.store.getState().loadModels();
  assert.equal(refreshed.store.getState().selectedModelId, 'jj');
  assert.equal(refreshed.store.getState().rainfallMode, 'real');
  assert.equal(refreshed.store.getState().selectedVersionId, 'jj-real-tuned');
  assert.equal(refreshed.store.getState().activeResultVersionId, 'jj-real-tuned');
});

test('Laocheng offers only design input and resets stale observed settings', async () => {
  const { store, calls } = fixture();
  await store.getState().loadModels();
  await store.getState().selectRainfallInput('real');
  await store.getState().selectModel('lc');
  await store.getState().selectRainfallInput('real');
  assert.equal(store.getState().rainfallMode, 'design');
  assert.equal(store.getState().selectedVersionId, 'lc-design');
  assert.equal(store.getState().rainfallOptions.read_only, false);
  assert.equal(calls.saves.length, 0);
});

test('reset restores the current observed baseline and keeps the input selected', async () => {
  const { store } = fixture();
  await store.getState().loadModels();
  await store.getState().selectRainfallInput('real');
  await store.getState().selectVersion('jj-real-tuned');
  await store.getState().restoreInitialState();
  assert.equal(store.getState().rainfallMode, 'real');
  assert.equal(store.getState().selectedVersionId, 'jj-real');
  assert.equal(store.getState().activeResultVersionId, null);
});

test('engineering saves derive from the selected observed input', async () => {
  const { store, calls } = fixture();
  await store.getState().loadModels();
  await store.getState().selectRainfallInput('real');
  await store
    .getState()
    .saveAdjustedVersion([
      { section: 'CONDUITS', target: 'C1', field: 'roughness', new_value: '0.02' },
    ]);
  assert.equal(calls.saves.length, 1);
  assert.equal(calls.saves[0].parent, 'jj-real');
  assert.equal(calls.saves[0].rainfall, undefined);
  assert.equal(store.getState().selectedVersionId, 'jj-real-new');
  assert.ok(store.getState().versions.every((version) => version.rainfall_mode === 'real'));
});

test('late responses from a previous input cannot restore stale parameters', async () => {
  const { store, api } = fixture();
  await store.getState().loadModels();
  const original = api.fetchEditableParameters;
  let finishReal;
  api.fetchEditableParameters = async (id) =>
    id === 'jj-real'
      ? new Promise((resolve) => {
          finishReal = () => resolve(original(id));
        })
      : original(id);
  const pending = store.getState().selectRainfallInput('real');
  await store.getState().selectRainfallInput('design');
  finishReal();
  await pending;
  assert.equal(store.getState().rainfallMode, 'design');
  assert.equal(store.getState().selectedVersionId, 'jj-design');
  assert.equal(store.getState().rainfallOptions.read_only, false);
  assert.equal(store.getState().loading, false);
});
