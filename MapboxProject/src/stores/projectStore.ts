import { defineStore } from 'pinia'

// 定义接口
interface ProjectState {
  currentProjectId: string | null
  currentOutId: string | null
  currentInpFilename: string | null
  projectHistory: string[]
  outIdHistory: string[]
  inpFilenameHistory: string[]
}

export const useProjectStore = defineStore('project', {
  state: (): ProjectState => ({
    currentProjectId: null,
    currentOutId: null,
    currentInpFilename: null,
    projectHistory: [],
    outIdHistory: [],
    inpFilenameHistory: [],
  }),

  getters: {
    getCurrentProjectId: (state): string | null => state.currentProjectId,
    getCurrentOutId: (state): string | null => state.currentOutId,
    getCurrentInpFilename: (state): string | null => state.currentInpFilename,
    getInpFilenameHistory: (state): string[] => state.inpFilenameHistory,
    hasProject: (state): boolean => state.currentProjectId !== null,
    hasOutId: (state): boolean => state.currentOutId !== null,
  },

  actions: {
    setProjectId(projectId: string): void {
      this.currentProjectId = projectId
      if (projectId && !this.projectHistory.includes(projectId)) {
        this.projectHistory.push(projectId)
      }
    },

    setOutId(outId: string): void {
      this.currentOutId = outId
      if (outId && !this.outIdHistory.includes(outId)) {
        this.outIdHistory.push(outId)
      }
    },

    setInpFilename(filename: string): void {
      if (this.currentInpFilename && this.currentInpFilename !== filename) {
        this.inpFilenameHistory.push(this.currentInpFilename)
      }
      this.currentInpFilename = filename
    },

    clearProject(): void {
      this.currentProjectId = null
    },

    clearOutId(): void {
      this.currentOutId = null
    },

    clearInpFilename(): void {
      this.currentInpFilename = null
      this.inpFilenameHistory = []
    },

    getProjectHistory(): string[] {
      return this.projectHistory
    },

    getOutIdHistory(): string[] {
      return this.outIdHistory
    },
  },
})
