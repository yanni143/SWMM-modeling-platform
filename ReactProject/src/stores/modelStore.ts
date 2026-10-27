import { create } from 'zustand'
import {
  createAdjustedVersion, fetchEditableParameters, fetchModelResults, fetchModels, fetchSection,
  fetchSections, fetchVersions, runProjectVersion,
  type EditableGroup, type ModelResultSummary, type ModelSummary, type ModelVersion,
  type ParameterChangeInput, type RainfallOptions, type RainfallOptionsInput, type SectionDetail,
  type SectionSummary, type SimulationOptions, type SimulationOptionsInput,
} from '@/api/models'
import { clearWorkspaceState, loadWorkspaceState, saveWorkspaceState } from '@/utils/workspaceState'

interface ModelState {
  models: ModelSummary[]; selectedModelId: string | null; versions: ModelVersion[]; selectedVersionId: string | null
  sections: SectionSummary[]; selectedSectionName: string | null; sectionDetail: SectionDetail | null
  loading: boolean; running: boolean; savingVersion: boolean; parameterGroups: EditableGroup[]
  simulationOptions: SimulationOptions | null; rainfallOptions: RainfallOptions | null
  availableResults: ModelResultSummary[]; activeResultVersionId: string | null; error: string | null
  loadModels: (selectInitialModel?: boolean) => Promise<void>; selectModel: (id: string) => Promise<void>
  selectVersion: (id: string) => Promise<void>; selectSection: (name: string) => Promise<void>
  runSelectedVersion: () => Promise<Awaited<ReturnType<typeof runProjectVersion>> | null>
  loadModelResults: () => Promise<void>; activateResultVersion: (id: string | null) => void
  restoreInitialState: () => Promise<void>
  saveAdjustedVersion: (changes: ParameterChangeInput[], summary?: string, simulation?: SimulationOptionsInput, rainfall?: RainfallOptionsInput) => Promise<{ version: ModelVersion; parentVersionId: string } | null>
}

const errorText = (error: unknown, fallback: string) => error instanceof Error ? error.message : fallback

export const useModelStore = create<ModelState>((set, get) => ({
  models: [], selectedModelId: null, versions: [], selectedVersionId: null, sections: [],
  selectedSectionName: null, sectionDetail: null, loading: false, running: false, savingVersion: false,
  parameterGroups: [], simulationOptions: null, rainfallOptions: null, availableResults: [],
  activeResultVersionId: null, error: null,
  async loadModels(selectInitialModel = true) {
    set({ loading: true, error: null })
    try {
      const models = await fetchModels(); set({ models })
      const savedModelId = loadWorkspaceState().selectedModelId
      const initialModel = models.find((model) => model.id === savedModelId) ?? models[0]
      if (!initialModel) throw new Error('研究区尚未初始化')
      if (selectInitialModel) await get().selectModel(initialModel.id)
    } catch (error) { set({ error: errorText(error, '研究区加载失败') }) }
    finally { set({ loading: false }) }
  },
  async selectModel(modelId) {
    saveWorkspaceState({ selectedModelId: modelId })
    set({ selectedModelId: modelId, selectedVersionId: null, versions: [], sections: [], sectionDetail: null, parameterGroups: [], simulationOptions: null, rainfallOptions: null, availableResults: [], activeResultVersionId: null, loading: true, error: null })
    try {
      const versions = await fetchVersions(modelId)
      if (get().selectedModelId !== modelId) return
      set({ versions })
      const saved = loadWorkspaceState().selectedVersionId
      const initial = versions.find((item) => item.id === saved) ?? versions.find((item) => item.version === 1) ?? versions[0]
      if (initial) await get().selectVersion(initial.id)
      await get().loadModelResults()
    } catch (error) { if (get().selectedModelId === modelId) set({ error: errorText(error, '工程版本加载失败') }) }
    finally { if (get().selectedModelId === modelId) set({ loading: false }) }
  },
  async selectVersion(versionId) {
    set({ selectedVersionId: versionId, selectedSectionName: null, sectionDetail: null, loading: true, error: null })
    try {
      const [sections, editable] = await Promise.all([fetchSections(versionId), fetchEditableParameters(versionId)])
      if (get().selectedVersionId !== versionId) return
      set({ sections, parameterGroups: editable.groups, simulationOptions: editable.simulation_options, rainfallOptions: editable.rainfall_options })
      saveWorkspaceState({ selectedVersionId: versionId })
    } catch (error) { if (get().selectedVersionId === versionId) set({ error: errorText(error, 'INP 分区读取失败') }) }
    finally { if (get().selectedVersionId === versionId) set({ loading: false }) }
  },
  async selectSection(sectionName) {
    const id = get().selectedVersionId; if (!id) return
    set({ selectedSectionName: sectionName, loading: true, error: null })
    try { set({ sectionDetail: await fetchSection(id, sectionName) }) }
    catch (error) { set({ error: errorText(error, '参数记录读取失败') }) }
    finally { set({ loading: false }) }
  },
  async runSelectedVersion() {
    const version = get().versions.find((item) => item.id === get().selectedVersionId); if (!version) return null
    set({ running: true, error: null })
    try { const result = await runProjectVersion(version.id); await get().loadModelResults(); get().activateResultVersion(version.id); return result }
    catch (error) { set({ error: errorText(error, '工程运行失败') }); return null }
    finally { set({ running: false }) }
  },
  async loadModelResults() {
    const modelId = get().selectedModelId
    try {
      const availableResults = await fetchModelResults(modelId ?? undefined); const saved = loadWorkspaceState().activeResultVersionId
      if (get().selectedModelId !== modelId) return
      set({ availableResults, activeResultVersionId: availableResults.some((item) => item.version_id === saved) ? saved ?? null : null })
    } catch (error) { if (get().selectedModelId === modelId) set({ error: errorText(error, '历史模拟结果加载失败') }) }
  },
  activateResultVersion(versionId) {
    if (versionId && !get().availableResults.some((item) => item.version_id === versionId)) return
    set({ activeResultVersionId: versionId }); saveWorkspaceState({ activeResultVersionId: versionId })
  },
  async restoreInitialState() {
    clearWorkspaceState(); set({ activeResultVersionId: null })
    const baseline = get().versions.find((item) => item.version === 1); if (baseline) await get().selectVersion(baseline.id)
  },
  async saveAdjustedVersion(changes, summary, simulation, rainfall) {
    const { selectedVersionId, selectedModelId } = get(); if (!selectedVersionId || !selectedModelId) return null
    set({ savingVersion: true, error: null })
    try {
      const result = await createAdjustedVersion(selectedVersionId, changes, summary, simulation, rainfall)
      set({ versions: await fetchVersions(selectedModelId) }); await get().selectVersion(result.version.id); await get().loadModels(false)
      return { version: result.version, parentVersionId: selectedVersionId }
    } catch (error) { set({ error: errorText(error, '新版本生成失败') }); return null }
    finally { set({ savingVersion: false }) }
  },
}))
