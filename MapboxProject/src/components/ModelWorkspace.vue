<template>
  <aside class="model-workspace" aria-label="工程工作台">
    <div class="workspace-heading">
      <div>
        <p class="workspace-kicker">FIXED STUDY AREA / 01</p>
        <h2>{{ store.selectedModel?.name || '模型工作台' }}</h2>
      </div>
      <span class="system-state"><i></i> INP READY</span>
    </div>

    <ol class="process-rail" aria-label="工程准备流程">
      <li class="active"><span>01</span>内置基线</li>
      <li :class="{ active: store.selectedVersionId }"><span>02</span>版本管理</li>
      <li :class="{ active: store.parameterGroups.length }"><span>03</span>运行调参</li>
    </ol>

    <p v-if="store.error" class="error-message" role="alert">{{ store.error }}</p>

    <section v-if="store.selectedModel" class="study-area-summary">
      <div class="section-title">
        <span>固定研究区</span>
        <button type="button" @click="store.loadModels()">刷新</button>
      </div>
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

async function runCurrentVersion() {
  const result = await store.runSelectedVersion()
  if (result) eventBus.emit('modelRunCompleted', result)
}

function formatBytes(value: number | null) {
  if (value === null) return '大小未知'
  if (value < 1024) return `${value} B`
  return `${(value / 1024).toFixed(1)} KB`
}
</script>

<style scoped src="@/assets/css/ModelWorkspace.css"></style>
