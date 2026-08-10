import { defineStore } from 'pinia'
import {
  fetchModels,
  fetchSection,
  fetchSections,
  fetchVersions,
  uploadModel,
  type ModelSummary,
  type ModelVersion,
  type SectionDetail,
  type SectionSummary,
} from '@/api/models'

interface ModelState {
  models: ModelSummary[]
  selectedModelId: string | null
  versions: ModelVersion[]
  selectedVersionId: string | null
  sections: SectionSummary[]
  selectedSectionName: string | null
  sectionDetail: SectionDetail | null
  loading: boolean
  uploading: boolean
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
    uploading: false,
    error: null,
  }),
  getters: {
    selectedModel: (state) =>
      state.models.find((model) => model.id === state.selectedModelId) ?? null,
    selectedVersion: (state) =>
      state.versions.find((version) => version.id === state.selectedVersionId) ?? null,
  },
  actions: {
    async loadModels() {
      this.loading = true
      this.error = null
      try {
        this.models = await fetchModels()
      } catch (error) {
        this.error = error instanceof Error ? error.message : '模型列表加载失败'
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
        const latest = this.versions[0]
        if (latest) await this.selectVersion(latest.id)
      } catch (error) {
        this.error = error instanceof Error ? error.message : '模型版本加载失败'
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
    async importModel(input: { name: string; description?: string; file: File }) {
      this.uploading = true
      this.error = null
      try {
        const imported = await uploadModel(input)
        await this.loadModels()
        this.selectedModelId = imported.model.id
        this.versions = [imported.version]
        this.selectedVersionId = imported.version.id
        this.sections = imported.sections
        return true
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'INP 导入失败'
        return false
      } finally {
        this.uploading = false
      }
    },
  },
})
