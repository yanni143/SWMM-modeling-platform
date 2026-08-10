<template>
  <aside class="model-workspace" aria-label="工程工作台">
    <div class="workspace-heading">
      <div>
        <p class="workspace-kicker">PROJECT INTAKE / 01</p>
        <h2>工程工作台</h2>
      </div>
      <span class="system-state"><i></i> INP READY</span>
    </div>

    <ol class="process-rail" aria-label="工程准备流程">
      <li class="active"><span>01</span>导入文件</li>
      <li :class="{ active: store.selectedVersionId }"><span>02</span>初始版本</li>
      <li :class="{ active: store.sections.length }"><span>03</span>参数索引</li>
    </ol>

    <form class="upload-form" @submit.prevent="submitImport">
      <label>
        <span>工程名称</span>
        <input v-model.trim="modelName" required maxlength="200" placeholder="例如：汾湖现状排水工程" />
      </label>
      <label>
        <span>INP 文件</span>
        <input ref="fileInput" type="file" required accept=".inp" @change="pickFile" />
      </label>
      <label>
        <span>备注 <small>可选</small></span>
        <textarea v-model.trim="description" maxlength="2000" rows="2" placeholder="工程来源、适用场景等"></textarea>
      </label>
      <button class="primary-action" type="submit" :disabled="store.uploading || !selectedFile">
        {{ store.uploading ? '正在校验并归档…' : '导入并建立 V1' }}
      </button>
    </form>

    <p v-if="store.error" class="error-message" role="alert">{{ store.error }}</p>

    <section class="ledger-section">
      <div class="section-title">
        <span>工程管理</span>
        <button type="button" @click="store.loadModels">刷新</button>
      </div>
      <select
        class="ledger-select"
        :value="store.selectedModelId || ''"
        aria-label="选择工程"
        @change="changeModel"
      >
        <option value="">{{ store.loading ? '正在读取…' : '选择一个工程' }}</option>
        <option v-for="model in store.models" :key="model.id" :value="model.id">
          {{ model.name }} · {{ model.version_count }} 个版本
        </option>
      </select>

      <div v-if="store.selectedModel" class="model-facts">
        <div><span>状态</span><strong>{{ store.selectedModel.status }}</strong></div>
        <div><span>最新版本</span><strong>V{{ store.selectedModel.latest_version ?? '—' }}</strong></div>
        <div><span>更新时间</span><strong>{{ formatDate(store.selectedModel.updated_at) }}</strong></div>
      </div>
    </section>

    <section v-if="store.versions.length" class="ledger-section">
      <div class="section-title"><span>版本与参数分区</span><em>只读准备阶段</em></div>
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

      <div class="section-index">
        <button
          v-for="section in store.sections"
          :key="section.name"
          type="button"
          :class="{ selected: store.selectedSectionName === section.name }"
          @click="store.selectSection(section.name)"
        >
          <span>[{{ section.name }}]</span>
          <b>{{ section.record_count }}</b>
          <i :class="{ editable: section.editable }">{{ section.editable ? '可调' : '结构' }}</i>
        </button>
      </div>
    </section>

    <section v-if="store.sectionDetail" class="parameter-preview">
      <div class="section-title">
        <span>[{{ store.sectionDetail.name }}]</span>
        <em>{{ store.sectionDetail.record_count }} 条记录</em>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th v-for="field in store.sectionDetail.fields" :key="field">{{ field }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in store.sectionDetail.records.slice(0, 30)" :key="record.index">
              <td v-for="field in store.sectionDetail.fields" :key="field">
                {{ record.values[field] ?? '—' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="store.sectionDetail.record_count > 30" class="preview-note">当前预览前 30 条记录</p>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useModelStore } from '@/stores/modelStore'
import eventBus from '@/eventBus'

const store = useModelStore()
const modelName = ref('')
const description = ref('')
const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

onMounted(() => store.loadModels())

function pickFile(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
  if (!modelName.value && selectedFile.value) {
    modelName.value = selectedFile.value.name.replace(/\.inp$/i, '')
  }
}

async function submitImport() {
  if (!selectedFile.value || !modelName.value) return
  const success = await store.importModel({
    name: modelName.value,
    description: description.value || undefined,
    file: selectedFile.value,
  })
  if (success) {
    modelName.value = ''
    description.value = ''
    selectedFile.value = null
    if (fileInput.value) fileInput.value.value = ''
  }
}

function changeModel(event: Event) {
  const modelId = (event.target as HTMLSelectElement).value
  if (modelId) store.selectModel(modelId)
}

function changeVersion(event: Event) {
  const versionId = (event.target as HTMLSelectElement).value
  if (versionId) store.selectVersion(versionId)
}

async function runCurrentVersion() {
  const result = await store.runSelectedVersion()
  if (result) eventBus.emit('modelRunCompleted', result)
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(new Date(value))
}

function formatBytes(value: number | null) {
  if (value === null) return '大小未知'
  if (value < 1024) return `${value} B`
  return `${(value / 1024).toFixed(1)} KB`
}
</script>

<style scoped src="@/assets/css/ModelWorkspace.css"></style>
