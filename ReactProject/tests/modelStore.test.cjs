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
      baseline_version_id: 'jj-design',
      rainfall_inputs: [
        { mode: 'design', baseline_version_id: 'jj-design' },
        { mode: 'real', baseline_version_id: 'jj-real' },
      ],
    },
    {
      id: 'lc',
      name: 'LC',
      baseline_version_id: 'lc-design',
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
        mode: versions.jj.find((version) => version.id === id)?.rainfall_mode ?? 'design',
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
      const version = { id: 'jj-new', version: 5, rainfall_mode: rainfall?.mode ?? 'real' };
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

test('one baseline exposes all legacy versions and results without creating versions', async () => {
  const { store, calls } = fixture();
  await store.getState().loadModels();
  assert.equal(store.getState().selectedVersionId, 'jj-design');
  assert.equal(store.getState().versions.length, 4);
  assert.equal(store.getState().availableResults.length, 4);
  await store.getState().selectVersion('jj-real-tuned');
  await store.getState().runSelectedVersion();
  assert.deepEqual(calls.runs, ['jj-real-tuned']);
  assert.equal(calls.saves.length, 0);
});

test('refresh restores versions and results by study area across rain sources', async () => {
  const first = fixture();
  await first.store.getState().loadModels();
  await first.store.getState().selectVersion('jj-real-tuned');
  first.store.getState().activateResultVersion('jj-real-tuned');
  await first.store.getState().selectModel('lc');
  await first.store.getState().selectModel('jj');
  assert.equal(first.store.getState().selectedVersionId, 'jj-real-tuned');
  const refreshed = fixture(first.saved());
  await refreshed.store.getState().loadModels();
  assert.equal(refreshed.store.getState().selectedVersionId, 'jj-real-tuned');
  assert.equal(refreshed.store.getState().activeResultVersionId, 'jj-real-tuned');
});

test('reset always restores the sole V1 baseline and clears the active result', async () => {
  const { store } = fixture();
  await store.getState().loadModels();
  await store.getState().selectVersion('jj-real-tuned');
  store.getState().activateResultVersion('jj-real-tuned');
  await store.getState().restoreInitialState();
  assert.equal(store.getState().selectedVersionId, 'jj-design');
  assert.equal(store.getState().activeResultVersionId, null);
});

test('custom rainfall save derives from the current engineering version', async () => {
  const { store, calls } = fixture();
  await store.getState().loadModels();
  await store.getState().selectVersion('jj-design-tuned');
  const rain = { mode: 'custom', start_seconds: 0, time_step_seconds: 300, values_mm: [1, 2, 0] };
  await store.getState().saveAdjustedVersion([], undefined, undefined, rain);
  assert.equal(calls.saves[0].parent, 'jj-design-tuned');
  assert.deepEqual(calls.saves[0].rainfall, rain);
  assert.equal(store.getState().selectedVersionId, 'jj-new');
  assert.equal(store.getState().rainfallOptions.mode, 'custom');
  assert.equal(store.getState().versions.length, 5);
});

test('engineering saves inherit rainfall and do not submit another sequence', async () => {
  const { store, calls } = fixture();
  await store.getState().loadModels();
  await store.getState().selectVersion('jj-real-tuned');
  await store
    .getState()
    .saveAdjustedVersion([
      { section: 'CONDUITS', target: 'C1', field: 'roughness', new_value: '0.02' },
    ]);
  assert.equal(calls.saves[0].parent, 'jj-real-tuned');
  assert.equal(calls.saves[0].rainfall, undefined);
});

test('pending changes prevent accidentally running the saved input', async () => {
  const { store, calls } = fixture();
  await store.getState().loadModels();
  store.getState().setPendingChanges(true);
  assert.equal(await store.getState().runSelectedVersion(), null);
  assert.equal(calls.runs.length, 0);
  store.getState().setPendingChanges(false);
  await store.getState().runSelectedVersion();
  assert.deepEqual(calls.runs, ['jj-design']);
});

test('stale responses cannot overwrite the currently selected version', async () => {
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
  const pending = store.getState().selectVersion('jj-real');
  await store.getState().selectVersion('jj-design');
  finishReal();
  await pending;
  assert.equal(store.getState().selectedVersionId, 'jj-design');
  assert.equal(store.getState().rainfallOptions.mode, 'design');
  assert.equal(store.getState().loading, false);
});
