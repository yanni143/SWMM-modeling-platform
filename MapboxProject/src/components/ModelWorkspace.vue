<template>
  <aside class="model-workspace" aria-label="工程工作台">
    <div class="workspace-heading">
      <div>
        <p class="workspace-kicker">FIXED STUDY AREA / 01</p>
        <h2>{{ store.selectedModel?.name || '模型工作台' }}</h2>
      </div>
      <div class="workspace-status">
        <span class="system-state"><i></i> INP READY</span>
        <button type="button" @click="store.loadModels()">刷新</button>
      </div>
    </div>

    <p v-if="store.error" class="error-message" role="alert">{{ store.error }}</p>

    <section v-if="store.selectedModel" class="study-area-summary">
      <div class="model-facts">
        <div><span>状态</span><strong>已就绪</strong></div>
        <div><span>版本数</span><strong>{{ store.selectedModel.version_count }}</strong></div>
        <div><span>最新版本</span><strong>V{{ store.selectedModel.latest_version ?? '—' }}</strong></div>
      </div>
    </section>

    <section v-if="store.versions.length" class="ledger-section">
      <div class="section-title"><span>工程版本</span><em>每次调参生成新版本</em></div>
      <select
        class="ledger-select"
        :value="store.selectedVersionId || ''"
        aria-label="选择工程版本"
        @change="changeVersion"
      >
        <option v-for="version in store.versions" :key="version.id" :value="version.id">
          V{{ version.version }} · {{ formatBytes(version.size_bytes) }}
        </option>
      </select>
      <button
        class="run-action"
        type="button"
        :disabled="store.running || !store.selectedVersionId"
        @click="runCurrentVersion"
      >
        {{ store.running ? '正在运行并解析结果…' : '运行当前版本' }}
      </button>
    </section>

    <section v-if="store.availableResults.length" class="ledger-section">
      <div class="section-title"><span>历史模拟结果</span><em>每个版本保留最新结果</em></div>
      <select
        class="ledger-select"
        :value="store.activeResultVersionId || ''"
        :disabled="store.running"
        aria-label="选择要显示的模拟结果版本"
        @change="changeResultVersion"
      >
        <option value="" disabled>选择一个结果版本</option>
        <option
          v-for="result in store.availableResults"
          :key="result.version_id"
          :value="result.version_id"
        >
          V{{ result.version }} · {{ formatResultTime(result.finished_at || result.created_at) }}
        </option>
      </select>
    </section>

    <button
      class="reset-action"
      type="button"
      :disabled="store.running"
      @click="restoreInitialState"
    >
      恢复初始状态
    </button>
    <ParameterTuning v-if="store.selectedVersionId && store.parameterGroups.length" />
  </aside>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useModelStore } from '@/stores/modelStore'
import eventBus from '@/eventBus'
import ParameterTuning from './ParameterTuning.vue'

const store = useModelStore()

onMounted(() => store.loadModels())

function changeVersion(event: Event) {
  const versionId = (event.target as HTMLSelectElement).value
  if (versionId) store.selectVersion(versionId)
}

function changeResultVersion(event: Event) {
  const versionId = (event.target as HTMLSelectElement).value
  if (versionId) store.activateResultVersion(versionId)
}

async function runCurrentVersion() {
  const result = await store.runSelectedVersion()
  if (result) eventBus.emit('modelRunCompleted', result)
}

async function restoreInitialState() {
  await store.restoreInitialState()
  eventBus.emit('workspaceReset', null)
}

function formatResultTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function formatBytes(value: number | null) {
  if (value === null) return '大小未知'
  if (value < 1024) return `${value} B`
  return `${(value / 1024).toFixed(1)} KB`
}
</script>

<style scoped src="@/assets/css/ModelWorkspace.css"></style>
