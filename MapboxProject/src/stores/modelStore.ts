import { acceptHMRUpdate, defineStore } from 'pinia'
import {
  fetchModels,
  fetchSection,
  fetchSections,
  fetchVersions,
  fetchEditableParameters,
  fetchModelResults,
  createAdjustedVersion,
  runProjectVersion,
  type ModelSummary,
  type ModelResultSummary,
  type ModelVersion,
  type SectionDetail,
  type SectionSummary,
  type EditableGroup,
  type ParameterChangeInput,
} from '@/api/models'
import {
  clearWorkspaceState,
  loadWorkspaceState,
  saveWorkspaceState,
} from '@/utils/workspaceState'

interface ModelState {
  models: ModelSummary[]
  selectedModelId: string | null
  versions: ModelVersion[]
  selectedVersionId: string | null
  sections: SectionSummary[]
  selectedSectionName: string | null
  sectionDetail: SectionDetail | null
  loading: boolean
  running: boolean
  savingVersion: boolean
  parameterGroups: EditableGroup[]
  availableResults: ModelResultSummary[]
  activeResultVersionId: string | null
  error: string | null
}

export const useModelStore = defineStore('model-library', {
  state: (): ModelState => ({
    models: [],
    selectedModelId: null,
    versions: [],
    selectedVersionId: null,
    sections: [],
    selectedSectionName: null,
    sectionDetail: null,
    loading: false,
    running: false,
    savingVersion: false,
    parameterGroups: [],
    availableResults: [],
    activeResultVersionId: null,
    error: null,
  }),
  getters: {
    selectedModel: (state) =>
      state.models.find((model) => model.id === state.selectedModelId) ?? null,
    selectedVersion: (state) =>
      state.versions.find((version) => version.id === state.selectedVersionId) ?? null,
  },
  actions: {
    async loadModels(selectFixedModel = true) {
      this.loading = true
      this.error = null
      try {
        this.models = await fetchModels()
        const fixedModel = this.models[0]
        if (!fixedModel) throw new Error('系统内置研究区尚未初始化')
        if (selectFixedModel) {
          await this.selectModel(fixedModel.id)
          await this.loadModelResults()
        }
      } catch (error) {
        this.error = error instanceof Error ? error.message : '内置研究区加载失败'
      } finally {
        this.loading = false
      }
    },
    async selectModel(modelId: string) {
      this.selectedModelId = modelId
      this.selectedVersionId = null
      this.sections = []
      this.sectionDetail = null
      this.loading = true
      this.error = null
      try {
        this.versions = await fetchVersions(modelId)
        const savedVersionId = loadWorkspaceState().selectedVersionId
        const initialVersion =
          this.versions.find((version) => version.id === savedVersionId) ??
          this.versions.find((version) => version.version === 1) ??
          this.versions[0]
        if (initialVersion) await this.selectVersion(initialVersion.id)
      } catch (error) {
        this.error = error instanceof Error ? error.message : '工程版本加载失败'
      } finally {
        this.loading = false
      }
    },
    async selectVersion(versionId: string) {
      this.selectedVersionId = versionId
      this.selectedSectionName = null
      this.sectionDetail = null
      this.loading = true
      this.error = null
      try {
        this.sections = await fetchSections(versionId)
        this.parameterGroups = await fetchEditableParameters(versionId)
        saveWorkspaceState({ selectedVersionId: versionId })
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'INP 分区读取失败'
      } finally {
        this.loading = false
      }
    },
    async selectSection(sectionName: string) {
      if (!this.selectedVersionId) return
      this.selectedSectionName = sectionName
      this.loading = true
      this.error = null
      try {
        this.sectionDetail = await fetchSection(this.selectedVersionId, sectionName)
      } catch (error) {
        this.error = error instanceof Error ? error.message : '参数记录读取失败'
      } finally {
        this.loading = false
      }
    },
    async runSelectedVersion() {
      const version = this.selectedVersion
      if (!version) return null
      this.running = true
      this.error = null
      try {
        const result = await runProjectVersion(version.id)
        await this.loadModelResults()
        this.activateResultVersion(version.id)
        return result
      } catch (error) {
        this.error = error instanceof Error ? error.message : '工程运行失败'
        return null
      } finally {
        this.running = false
      }
    },
    async loadModelResults() {
      try {
        this.availableResults = await fetchModelResults()
        const savedResultVersionId = loadWorkspaceState().activeResultVersionId
        this.activeResultVersionId = this.availableResults.some(
          (result) => result.version_id === savedResultVersionId,
        )
          ? savedResultVersionId || null
          : null
      } catch (error) {
        this.error = error instanceof Error ? error.message : '历史模拟结果加载失败'
      }
    },
    activateResultVersion(versionId: string | null) {
      if (
        versionId &&
        !this.availableResults.some((result) => result.version_id === versionId)
      ) return
      this.activeResultVersionId = versionId
      saveWorkspaceState({ activeResultVersionId: versionId })
    },
    async restoreInitialState() {
      clearWorkspaceState()
      this.activeResultVersionId = null
      const baseline = this.versions.find((version) => version.version === 1)
      if (baseline) await this.selectVersion(baseline.id)
    },
    async saveAdjustedVersion(changes: ParameterChangeInput[], summary?: string) {
      if (!this.selectedVersionId || !this.selectedModelId) return null
      const parentVersionId = this.selectedVersionId
      this.savingVersion = true
      this.error = null
      try {
        const result = await createAdjustedVersion(parentVersionId, changes, summary)
        this.versions = await fetchVersions(this.selectedModelId)
        await this.selectVersion(result.version.id)
        await this.loadModels(false)
        return { ...result, parentVersionId }
      } catch (error) {
        this.error = error instanceof Error ? error.message : '新版本生成失败'
        return null
      } finally {
        this.savingVersion = false
      }
    },
  },
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useModelStore, import.meta.hot))
}
