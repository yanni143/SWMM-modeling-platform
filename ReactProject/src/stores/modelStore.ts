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
  hasPendingChanges: boolean;
  setPendingChanges: (pending: boolean) => void;
  loadModels: (selectInitialModel?: boolean) => Promise<void>;
  selectModel: (id: string) => Promise<void>;
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
export const useModelStore = create<ModelState>((set, get) => ({
  models: [],
  selectedModelId: null,
  allVersions: [],
  versions: [],
  selectedVersionId: null,
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
  hasPendingChanges: false,
  setPendingChanges: (pending) => set({ hasPendingChanges: pending }),
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
      hasPendingChanges: false,
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
      set({ allVersions, versions: allVersions });
      const saved = loadWorkspaceState();
      const baseline = get().models.find((item) => item.id === modelId)?.baseline_version_id;
      const savedVersion = saved.selectedVersionsByModel?.[modelId];
      const initial =
        allVersions.find((item) => item.id === savedVersion) ??
        allVersions.find((item) => item.id === baseline) ??
        allVersions.find((item) => item.version === 1);
      if (!initial) throw new Error('研究区初始版本尚未初始化');
      await get().selectVersion(initial.id);
      if (get().selectedModelId === modelId) await get().loadModelResults();
    } catch (error) {
      if (get().selectedModelId === modelId) set({ error: errorText(error, '工程版本加载失败') });
    } finally {
      if (get().selectedModelId === modelId) set({ loading: false });
    }
  },
  async selectVersion(versionId) {
    if (!get().versions.some((version) => version.id === versionId)) return;
    const scope = get().selectedModelId;
    set({
      selectedVersionId: versionId,
      hasPendingChanges: false,
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
      if (get().selectedVersionId !== versionId || get().selectedModelId !== scope) return;
      set({
        sections,
        parameterGroups: editable.groups,
        simulationOptions: editable.simulation_options,
        rainfallOptions: editable.rainfall_options,
      });
      saveWorkspaceState({
        selectedVersionId: versionId,
        selectedVersionsByModel: {
          ...loadWorkspaceState().selectedVersionsByModel,
          [scope!]: versionId,
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
    if (get().hasPendingChanges) {
      set({ error: '请先保存或撤销当前修改，再运行版本' });
      return null;
    }
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
    const scope = modelId;
    if (!modelId) return;
    try {
      const results = await fetchModelResults(modelId ?? undefined);
      if (get().selectedModelId !== modelId) return;
      const ids = new Set(get().versions.map((version) => version.id));
      const availableResults = results.filter((result) => ids.has(result.version_id));
      const saved = loadWorkspaceState().activeResultsByModel?.[scope!] ?? null;
      set({
        availableResults,
        activeResultVersionId: availableResults.some((item) => item.version_id === saved)
          ? saved
          : null,
      });
    } catch (error) {
      if (get().selectedModelId === scope) set({ error: errorText(error, '历史模拟结果加载失败') });
    }
  },
  activateResultVersion(versionId) {
    if (versionId && !get().availableResults.some((item) => item.version_id === versionId)) return;
    const scope = get().selectedModelId;
    set({ activeResultVersionId: versionId });
    saveWorkspaceState({
      activeResultVersionId: versionId,
      activeResultsByModel: { ...loadWorkspaceState().activeResultsByModel, [scope!]: versionId },
    });
  },
  async restoreInitialState() {
    const { selectedModelId } = get();
    const baseline =
      get().models.find((model) => model.id === selectedModelId)?.baseline_version_id ??
      get().versions.find((version) => version.version === 1)?.id;
    const saved = loadWorkspaceState();
    clearWorkspaceState();
    saveWorkspaceState({
      selectedModelId: selectedModelId ?? undefined,
      selectedVersionsByModel: saved.selectedVersionsByModel,
      activeResultsByModel: { ...saved.activeResultsByModel, [selectedModelId!]: null },
    });
    set({ activeResultVersionId: null, hasPendingChanges: false });
    if (baseline) await get().selectVersion(baseline);
  },
  async saveAdjustedVersion(changes, summary, simulation, rainfall) {
    const { selectedVersionId, selectedModelId } = get();
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
        versions: allVersions,
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
