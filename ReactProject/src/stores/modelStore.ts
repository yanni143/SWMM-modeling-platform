import { create } from 'zustand';
import {
  createAdjustedVersion,
  fetchEditableParameters,
  fetchModelResults,
  fetchModels,
  fetchSection,
  fetchSections,
  fetchVersions,
  runProjectVersion,
  type EditableGroup,
  type ModelResultSummary,
  type ModelSummary,
  type ModelVersion,
  type ParameterChangeInput,
  type RainfallMode,
  type RainfallOptions,
  type RainfallOptionsInput,
  type SectionDetail,
  type SectionSummary,
  type SimulationOptions,
  type SimulationOptionsInput,
} from '@/api/models';
import {
  clearWorkspaceState,
  loadWorkspaceState,
  saveWorkspaceState,
} from '@/utils/workspaceState';

interface ModelState {
  models: ModelSummary[];
  selectedModelId: string | null;
  allVersions: ModelVersion[];
  versions: ModelVersion[];
  selectedVersionId: string | null;
  rainfallMode: RainfallMode;
  sections: SectionSummary[];
  selectedSectionName: string | null;
  sectionDetail: SectionDetail | null;
  loading: boolean;
  running: boolean;
  savingVersion: boolean;
  parameterGroups: EditableGroup[];
  simulationOptions: SimulationOptions | null;
  rainfallOptions: RainfallOptions | null;
  availableResults: ModelResultSummary[];
  activeResultVersionId: string | null;
  error: string | null;
  loadModels: (selectInitialModel?: boolean) => Promise<void>;
  selectModel: (id: string) => Promise<void>;
  selectRainfallInput: (mode: RainfallMode) => Promise<void>;
  selectVersion: (id: string) => Promise<void>;
  selectSection: (name: string) => Promise<void>;
  runSelectedVersion: () => Promise<Awaited<ReturnType<typeof runProjectVersion>> | null>;
  loadModelResults: () => Promise<void>;
  activateResultVersion: (id: string | null) => void;
  restoreInitialState: () => Promise<void>;
  saveAdjustedVersion: (
    changes: ParameterChangeInput[],
    summary?: string,
    simulation?: SimulationOptionsInput,
    rainfall?: RainfallOptionsInput,
  ) => Promise<{ version: ModelVersion; parentVersionId: string } | null>;
}

const errorText = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;
const versionMode = (version: ModelVersion): RainfallMode =>
  version.rainfall_mode ?? (version.change_summary?.rainfall_mode === 'real' ? 'real' : 'design');
const inputKey = (modelId: string | null, mode: RainfallMode) => `${modelId}:${mode}`;

export const useModelStore = create<ModelState>((set, get) => ({
  models: [],
  selectedModelId: null,
  allVersions: [],
  versions: [],
  selectedVersionId: null,
  rainfallMode: 'design',
  sections: [],
  selectedSectionName: null,
  sectionDetail: null,
  loading: false,
  running: false,
  savingVersion: false,
  parameterGroups: [],
  simulationOptions: null,
  rainfallOptions: null,
  availableResults: [],
  activeResultVersionId: null,
  error: null,
  async loadModels(selectInitialModel = true) {
    set({ loading: true, error: null });
    try {
      const models = await fetchModels();
      set({ models });
      const savedModelId = loadWorkspaceState().selectedModelId;
      const initialModel = models.find((model) => model.id === savedModelId) ?? models[0];
      if (!initialModel) throw new Error('研究区尚未初始化');
      if (selectInitialModel) await get().selectModel(initialModel.id);
    } catch (error) {
      set({ error: errorText(error, '研究区加载失败') });
    } finally {
      set({ loading: false });
    }
  },
  async selectModel(modelId) {
    saveWorkspaceState({ selectedModelId: modelId });
    set({
      selectedModelId: modelId,
      selectedVersionId: null,
      allVersions: [],
      versions: [],
      sections: [],
      sectionDetail: null,
      parameterGroups: [],
      simulationOptions: null,
      rainfallOptions: null,
      availableResults: [],
      activeResultVersionId: null,
      loading: true,
      error: null,
    });
    try {
      const allVersions = await fetchVersions(modelId);
      if (get().selectedModelId !== modelId) return;
      set({ allVersions });
      const model = get().models.find((item) => item.id === modelId);
      const saved = loadWorkspaceState().rainfallModes?.[modelId] ?? 'design';
      const mode = model?.rainfall_inputs.some((input) => input.mode === saved) ? saved : 'design';
      await get().selectRainfallInput(mode);
    } catch (error) {
      if (get().selectedModelId === modelId) set({ error: errorText(error, '工程版本加载失败') });
    } finally {
      if (get().selectedModelId === modelId) set({ loading: false });
    }
  },
  async selectRainfallInput(mode) {
    const modelId = get().selectedModelId;
    const model = get().models.find((item) => item.id === modelId);
    const input = model?.rainfall_inputs.find((item) => item.mode === mode);
    if (!modelId || !input) return;
    const versions = get().allVersions.filter((version) => versionMode(version) === mode);
    const scope = inputKey(modelId, mode);
    const saved = loadWorkspaceState();
    saveWorkspaceState({ rainfallModes: { ...saved.rainfallModes, [modelId]: mode } });
    set({
      rainfallMode: mode,
      versions,
      selectedVersionId: null,
      sections: [],
      sectionDetail: null,
      parameterGroups: [],
      simulationOptions: null,
      rainfallOptions: null,
      availableResults: [],
      activeResultVersionId: null,
      loading: true,
      error: null,
    });
    try {
      const savedVersion = saved.selectedVersionsByInput?.[scope] ?? saved.selectedVersionId;
      const initial =
        versions.find((item) => item.id === savedVersion) ??
        versions.find((item) => item.id === input.baseline_version_id);
      if (!initial) throw new Error('输入方案尚未初始化，请重启后端服务');
      await get().selectVersion(initial.id);
      if (get().selectedModelId !== modelId || get().rainfallMode !== mode) return;
      await get().loadModelResults();
    } catch (error) {
      if (get().selectedModelId === modelId && get().rainfallMode === mode)
        set({ error: errorText(error, '输入方案加载失败') });
    } finally {
      if (get().selectedModelId === modelId && get().rainfallMode === mode) set({ loading: false });
    }
  },
  async selectVersion(versionId) {
    if (!get().versions.some((version) => version.id === versionId)) return;
    const scope = inputKey(get().selectedModelId, get().rainfallMode);
    set({
      selectedVersionId: versionId,
      selectedSectionName: null,
      sectionDetail: null,
      loading: true,
      error: null,
    });
    try {
      const [sections, editable] = await Promise.all([
        fetchSections(versionId),
        fetchEditableParameters(versionId),
      ]);
      if (
        get().selectedVersionId !== versionId ||
        inputKey(get().selectedModelId, get().rainfallMode) !== scope
      )
        return;
      set({
        sections,
        parameterGroups: editable.groups,
        simulationOptions: editable.simulation_options,
        rainfallOptions: editable.rainfall_options,
      });
      saveWorkspaceState({
        selectedVersionId: versionId,
        selectedVersionsByInput: {
          ...loadWorkspaceState().selectedVersionsByInput,
          [scope]: versionId,
        },
      });
    } catch (error) {
      if (get().selectedVersionId === versionId)
        set({ error: errorText(error, 'INP 分区读取失败') });
    } finally {
      if (get().selectedVersionId === versionId) set({ loading: false });
    }
  },
  async selectSection(sectionName) {
    const id = get().selectedVersionId;
    if (!id) return;
    set({ selectedSectionName: sectionName, loading: true, error: null });
    try {
      set({ sectionDetail: await fetchSection(id, sectionName) });
    } catch (error) {
      set({ error: errorText(error, '参数记录读取失败') });
    } finally {
      set({ loading: false });
    }
  },
  async runSelectedVersion() {
    const version = get().versions.find((item) => item.id === get().selectedVersionId);
    if (!version) return null;
    set({ running: true, error: null });
    try {
      const result = await runProjectVersion(version.id);
      await get().loadModelResults();
      get().activateResultVersion(version.id);
      return result;
    } catch (error) {
      set({ error: errorText(error, '工程运行失败') });
      return null;
    } finally {
      set({ running: false });
    }
  },
  async loadModelResults() {
    const modelId = get().selectedModelId;
    const mode = get().rainfallMode;
    const scope = inputKey(modelId, mode);
    try {
      const results = await fetchModelResults(modelId ?? undefined);
      if (get().selectedModelId !== modelId || get().rainfallMode !== mode) return;
      const ids = new Set(get().versions.map((version) => version.id));
      const availableResults = results.filter((result) => ids.has(result.version_id));
      const saved = loadWorkspaceState().activeResultsByInput?.[scope] ?? null;
      set({
        availableResults,
        activeResultVersionId: availableResults.some((item) => item.version_id === saved)
          ? saved
          : null,
      });
    } catch (error) {
      if (inputKey(get().selectedModelId, get().rainfallMode) === scope)
        set({ error: errorText(error, '历史模拟结果加载失败') });
    }
  },
  activateResultVersion(versionId) {
    if (versionId && !get().availableResults.some((item) => item.version_id === versionId)) return;
    const scope = inputKey(get().selectedModelId, get().rainfallMode);
    set({ activeResultVersionId: versionId });
    saveWorkspaceState({
      activeResultVersionId: versionId,
      activeResultsByInput: { ...loadWorkspaceState().activeResultsByInput, [scope]: versionId },
    });
  },
  async restoreInitialState() {
    const { selectedModelId, rainfallMode } = get();
    const input = get()
      .models.find((model) => model.id === selectedModelId)
      ?.rainfall_inputs.find((item) => item.mode === rainfallMode);
    const saved = loadWorkspaceState();
    const scope = inputKey(selectedModelId, rainfallMode);
    clearWorkspaceState();
    saveWorkspaceState({
      selectedModelId: selectedModelId ?? undefined,
      rainfallModes: saved.rainfallModes,
      selectedVersionsByInput: saved.selectedVersionsByInput,
      activeResultsByInput: { ...saved.activeResultsByInput, [scope]: null },
    });
    set({ activeResultVersionId: null });
    if (input) await get().selectVersion(input.baseline_version_id);
  },
  async saveAdjustedVersion(changes, summary, simulation, rainfall) {
    const { selectedVersionId, selectedModelId, rainfallMode } = get();
    if (!selectedVersionId || !selectedModelId) return null;
    set({ savingVersion: true, error: null });
    try {
      const result = await createAdjustedVersion(
        selectedVersionId,
        changes,
        summary,
        simulation,
        rainfall,
      );
      const allVersions = await fetchVersions(selectedModelId);
      set({
        allVersions,
        versions: allVersions.filter((version) => versionMode(version) === rainfallMode),
      });
      await get().selectVersion(result.version.id);
      await get().loadModels(false);
      return { version: result.version, parentVersionId: selectedVersionId };
    } catch (error) {
      set({ error: errorText(error, '新版本生成失败') });
      return null;
    } finally {
      set({ savingVersion: false });
    }
  },
}));
