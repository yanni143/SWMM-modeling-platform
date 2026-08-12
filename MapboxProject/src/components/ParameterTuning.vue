<template>
  <section class="tuning-workspace" aria-label="参数设置">
    <div class="tuning-heading">
      <div>
        <h3>模拟参数设置</h3>
      </div>
      <span v-if="simulationOptionsChanged">
        {{ Number(simulationDurationChanged) + Number(reportStepChanged) }} 项待保存
      </span>
    </div>

    <div v-if="store.simulationOptions" class="simulation-settings">
      <div class="simulation-setting-fields">
        <label>
          <span>模拟时长 <small>秒</small></span>
          <input
            v-model.number="durationSeconds"
            type="number"
            :min="store.simulationOptions.duration_min_seconds"
            :max="store.simulationOptions.duration_max_seconds"
            step="1"
          />
          <small>
            {{ store.simulationOptions.duration_min_seconds }}～{{ store.simulationOptions.duration_max_seconds }} 秒
          </small>
        </label>
        <label>
          <span>输出步长 <small>秒</small></span>
          <input
            v-model.number="reportStepSeconds"
            type="number"
            :min="effectiveReportStepMinimum"
            :max="durationSeconds || undefined"
            step="1"
          />
          <small>不小于路由步长 {{ store.simulationOptions.routing_step_seconds }} 秒</small>
        </label>
      </div>
      <div class="simulation-projection">
        <span>预计结束</span>
        <strong>{{ estimatedEndTime }}</strong>
        <output>{{ estimatedOutputSteps }} 个输出点</output>
        <em v-if="store.simulationOptions.require_report_step_divisible">时长须能被输出步长整除</em>
      </div>
    </div>

    <div class="engineering-heading tuning-heading">
      <div>
        <h3>工程参数修改</h3>
      </div>
      <span v-if="draftsList.length">{{ draftsList.length }} 项待保存</span>
    </div>

    <p class="tuning-guidance">从地图或对象列表选择要素；批量模式只调整所选对象共有的参数。</p>

    <div class="selection-mode" aria-label="选择方式">
      <button type="button" :class="{ active: selectionMode === 'single' }" @click="setSelectionMode('single')">
        单个选择
      </button>
      <button type="button" :class="{ active: selectionMode === 'batch' }" @click="setSelectionMode('batch')">
        批量选择 <b v-if="selectedTargets.length">{{ selectedTargets.length }}</b>
      </button>
    </div>

    <div class="group-tabs" role="tablist" aria-label="对象类型">
      <button
        v-for="group in groups"
        :key="group.id"
        type="button"
        :class="{ active: group.id === selectedGroupId }"
        @click="selectGroup(group.id)"
      >
        {{ group.label }} <b>{{ group.objects.length }}</b>
      </button>
    </div>

    <div v-if="activeGroup" class="object-picker">
      <input v-model.trim="search" type="search" placeholder="搜索对象编号" aria-label="搜索对象编号" />
      <select v-if="selectionMode === 'single'" v-model="selectedTarget" size="5" aria-label="选择调参对象">
        <option v-for="item in filteredObjects" :key="item.target" :value="item.target">
          {{ item.target }}
        </option>
      </select>
      <div v-else class="batch-object-list">
        <div class="batch-list-actions">
          <button type="button" @click="selectFilteredObjects">全选搜索结果</button>
          <button type="button" @click="clearObjectSelection">清空</button>
        </div>
        <label v-for="item in filteredObjects" :key="item.target">
          <input
            type="checkbox"
            :checked="selectedTargets.includes(item.target)"
            @change="toggleTarget(item.target)"
          />
          <span>{{ item.target }}</span>
        </label>
        <p v-if="!filteredObjects.length">没有匹配对象</p>
      </div>
    </div>

    <div v-if="selectionMode === 'single' && selectedObject" class="object-editor">
      <div class="object-identity">
        <span>当前对象</span>
        <strong>{{ selectedObject.target }}</strong>
        <em>也可直接点击地图要素切换</em>
      </div>
      <div class="field-grid">
        <label v-for="field in selectedObject.fields" :key="field.key">
          <span>{{ field.label }} <small>{{ field.unit }}</small></span>
          <input
            type="number"
            :value="draftValue(field)"
            :min="field.minimum"
            :max="field.maximum"
            :step="field.step"
            @change="stageField(field, $event)"
          />
          <small>{{ field.minimum }} ～ {{ field.maximum }} {{ field.unit }}</small>
        </label>
      </div>
    </div>

    <div v-if="selectionMode === 'batch' && selectedTargets.length" class="batch-editor">
      <div class="batch-editor-heading">
        <div>
          <strong>已选择 {{ selectedTargets.length }} 个{{ activeGroup?.label }}</strong>
        </div>
      </div>
      <div v-if="commonFields.length" class="batch-controls">
        <label>
          <span>调整参数</span>
          <select v-model="batchFieldKey">
            <option v-for="field in commonFields" :key="field.key" :value="field.key">
              {{ field.label }} {{ field.unit ? `(${field.unit})` : '' }}
            </option>
          </select>
        </label>
        <label>
          <span>调整方式</span>
          <select v-model="batchOperation">
            <option value="set">设置为</option>
            <option value="add">增加 / 减少</option>
            <option value="percent">按比例调整</option>
          </select>
        </label>
        <label>
          <span>{{ batchOperation === 'percent' ? '调整比例' : '数值' }}</span>
          <div class="batch-value-input">
            <input v-model="batchAmount" type="number" :step="batchField?.step || 'any'" />
            <small>{{ batchOperation === 'percent' ? '%' : batchField?.unit }}</small>
          </div>
        </label>
        <button type="button" @click="applyBatchChange">计算并加入变更预览</button>
      </div>
      <p v-else class="no-common-fields">所选对象没有共同的可调参数，请选择同一种节点类型。</p>
    </div>

    <p v-if="displayError" class="tuning-error" role="alert">{{ displayError }}</p>

    <div v-if="pendingChangeCount" class="change-ruler">
      <div class="change-ruler-title">
        <span>变更预览</span>
        <button type="button" @click="clearDrafts">全部撤销</button>
      </div>
      <div v-if="simulationDurationChanged" class="change-line">
        <span>模拟时长</span>
        <code>{{ store.simulationOptions?.duration_seconds }} 秒</code>
        <i>→</i>
        <code>{{ durationSeconds }} 秒</code>
        <button type="button" aria-label="撤销模拟时长修改" @click="resetDuration">×</button>
      </div>
      <div v-if="reportStepChanged" class="change-line">
        <span>输出步长</span>
        <code>{{ store.simulationOptions?.report_step_seconds }} 秒</code>
        <i>→</i>
        <code>{{ reportStepSeconds }} 秒</code>
        <button type="button" aria-label="撤销输出步长修改" @click="resetReportStep">×</button>
      </div>
      <div v-for="draft in draftsList" :key="draft.key" class="change-line">
        <span>{{ draft.target }} · {{ draft.label }}</span>
        <code>{{ draft.oldValue }}</code>
        <i>→</i>
        <code>{{ draft.newValue }} {{ draft.unit }}</code>
        <button type="button" aria-label="撤销该项" @click="removeDraft(draft.key)">×</button>
      </div>
      <input v-model.trim="summary" maxlength="500" placeholder="版本说明，例如：降低管线粗糙度" />
      <button class="save-version" type="button" :disabled="store.savingVersion || !!simulationError" @click="saveVersion">
        {{ store.savingVersion ? '正在校验并生成…' : `校验并生成 V${nextVersionNumber}` }}
      </button>
    </div>

    <div v-if="createdVersion" class="version-created">
      <div>
        <strong>新版本 V{{ createdVersion.version }} 已生成</strong>
      </div>
      <button type="button" :disabled="store.running" @click="runCreatedVersion">
        {{ store.running ? '正在运行…' : `运行 V${createdVersion.version}` }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { EditableField, ModelVersion } from '@/api/models'
import eventBus from '@/eventBus'
import { useModelStore } from '@/stores/modelStore'

interface Draft {
  key: string
  section: string
  target: string
  field: string
  label: string
  unit: string
  oldValue: string
  newValue: string
}

const store = useModelStore()
const selectedGroupId = ref('')
const selectedTarget = ref('')
const selectedTargets = ref<string[]>([])
const selectionMode = ref<'single' | 'batch'>('single')
const search = ref('')
const summary = ref('')
const drafts = ref<Record<string, Draft>>({})
const localError = ref('')
const createdVersion = ref<ModelVersion | null>(null)
const batchFieldKey = ref('')
const batchOperation = ref<'set' | 'add' | 'percent'>('set')
const batchAmount = ref('')
const durationSeconds = ref(0)
const reportStepSeconds = ref(0)

const groups = computed(() => store.parameterGroups)
const activeGroup = computed(() => groups.value.find((group) => group.id === selectedGroupId.value))
const filteredObjects = computed(() => {
  const query = search.value.toLowerCase()
  return (activeGroup.value?.objects || []).filter((item) => item.target.toLowerCase().includes(query))
})
const selectedObject = computed(() =>
  activeGroup.value?.objects.find((item) => item.target === selectedTarget.value),
)
const selectedBatchObjects = computed(() =>
  (activeGroup.value?.objects || []).filter((item) => selectedTargets.value.includes(item.target)),
)
const commonFields = computed(() => {
  const objects = selectedBatchObjects.value
  const firstObject = objects[0]
  if (!firstObject) return []
  return firstObject.fields.filter((field) =>
    objects.every((item) => item.fields.some((candidate) => candidate.key === field.key)),
  )
})
const batchField = computed(() => commonFields.value.find((field) => field.key === batchFieldKey.value))
const filteredSelectedCount = computed(() =>
  filteredObjects.value.filter((item) => selectedTargets.value.includes(item.target)).length,
)
const draftsList = computed(() => Object.values(drafts.value))
const simulationDurationChanged = computed(
  () => durationSeconds.value !== store.simulationOptions?.duration_seconds,
)
const reportStepChanged = computed(
  () => reportStepSeconds.value !== store.simulationOptions?.report_step_seconds,
)
const simulationOptionsChanged = computed(
  () => simulationDurationChanged.value || reportStepChanged.value,
)
const pendingChangeCount = computed(
  () => draftsList.value.length + Number(simulationDurationChanged.value) + Number(reportStepChanged.value),
)
const effectiveReportStepMinimum = computed(() =>
  Math.max(
    store.simulationOptions?.report_step_min_seconds || 1,
    Math.ceil(store.simulationOptions?.routing_step_seconds || 0),
  ),
)
const estimatedOutputSteps = computed(() => {
  if (!Number.isInteger(durationSeconds.value) || !Number.isInteger(reportStepSeconds.value) || reportStepSeconds.value <= 0) return '—'
  return Math.floor(durationSeconds.value / reportStepSeconds.value)
})
const estimatedEndTime = computed(() => {
  const start = store.simulationOptions?.start_datetime
  if (!start || !Number.isInteger(durationSeconds.value) || durationSeconds.value <= 0) return '—'
  return formatDateTime(new Date(parseSimulationDate(start).getTime() + durationSeconds.value * 1000).toISOString())
})
const simulationError = computed(() => {
  const options = store.simulationOptions
  const duration = durationSeconds.value
  const reportStep = reportStepSeconds.value
  if (!options) return ''
  if (!Number.isInteger(duration)) return '模拟时长必须是整数秒'
  if (duration < options.duration_min_seconds || duration > options.duration_max_seconds) {
    return `模拟时长必须在 ${options.duration_min_seconds}～${options.duration_max_seconds} 秒之间`
  }
  if (!Number.isInteger(reportStep)) return '输出步长必须是整数秒'
  if (reportStep < effectiveReportStepMinimum.value) return `输出步长不能小于 ${effectiveReportStepMinimum.value} 秒`
  if (reportStep > duration) return '输出步长不能大于模拟时长'
  if (options.require_report_step_divisible && duration % reportStep !== 0) return '模拟时长必须能被输出步长整除'
  if (Math.floor(duration / reportStep) > options.max_output_steps) return `输出时间点不能超过 ${options.max_output_steps} 个`
  return ''
})
const displayError = computed(() => localError.value || simulationError.value)
const nextVersionNumber = computed(() => Math.max(...store.versions.map((item) => item.version), 0) + 1)

watch(
  () => store.simulationOptions,
  (options) => {
    durationSeconds.value = options?.duration_seconds || 0
    reportStepSeconds.value = options?.report_step_seconds || 0
  },
  { immediate: true },
)

watch(
  groups,
  (value) => {
    if (!value.some((group) => group.id === selectedGroupId.value)) {
      selectedGroupId.value = value[0]?.id || ''
      selectedTarget.value = value[0]?.objects[0]?.target || ''
    }
  },
  { immediate: true },
)

watch(activeGroup, (group) => {
  if (!group?.objects.some((item) => item.target === selectedTarget.value)) {
    selectedTarget.value = group?.objects[0]?.target || ''
  }
  selectedTargets.value = []
})

watch(commonFields, (fields) => {
  if (!fields.some((field) => field.key === batchFieldKey.value)) {
    batchFieldKey.value = fields[0]?.key || ''
  }
})

watch(
  () => store.selectedVersionId,
  () => {
    clearDrafts()
    createdVersion.value = null
  },
)

function selectGroup(groupId: string) {
  selectedGroupId.value = groupId
  search.value = ''
}

function setSelectionMode(mode: 'single' | 'batch') {
  selectionMode.value = mode
  localError.value = ''
  if (mode === 'batch' && !selectedTargets.value.length && selectedTarget.value) {
    selectedTargets.value = [selectedTarget.value]
  }
}

function toggleTarget(target: string) {
  selectedTargets.value = selectedTargets.value.includes(target)
    ? selectedTargets.value.filter((item) => item !== target)
    : [...selectedTargets.value, target]
}

function selectFilteredObjects() {
  selectedTargets.value = Array.from(
    new Set([...selectedTargets.value, ...filteredObjects.value.map((item) => item.target)]),
  )
}

function clearObjectSelection() {
  selectedTargets.value = []
}

function draftKey(field: EditableField) {
  return `${field.section}|${selectedObject.value?.target}|${field.field}`
}

function draftKeyFor(target: string, field: EditableField) {
  return `${field.section}|${target}|${field.field}`
}

function draftValue(field: EditableField) {
  return drafts.value[draftKey(field)]?.newValue ?? field.value
}

function stageField(field: EditableField, event: Event) {
  const input = event.target as HTMLInputElement
  const value = Number(input.value)
  localError.value = ''
  if (!Number.isFinite(value) || value < field.minimum || value > field.maximum) {
    localError.value = `${field.label}必须在 ${field.minimum}～${field.maximum} ${field.unit} 之间`
    input.value = draftValue(field)
    return
  }
  const normalized = String(value)
  const key = draftKey(field)
  if (normalized === String(Number(field.value))) {
    removeDraft(key)
    return
  }
  drafts.value[key] = {
    key,
    section: field.section,
    target: selectedObject.value!.target,
    field: field.field,
    label: field.label,
    unit: field.unit,
    oldValue: field.value,
    newValue: normalized,
  }
}

function applyBatchChange() {
  const fieldTemplate = batchField.value
  const amount = Number(batchAmount.value)
  localError.value = ''
  if (!fieldTemplate || !Number.isFinite(amount)) {
    localError.value = '请选择参数并输入有效数值'
    return
  }

  const updates: Array<{ key: string; draft?: Draft }> = []
  for (const item of selectedBatchObjects.value) {
    const field = item.fields.find((candidate) => candidate.key === fieldTemplate.key)
    if (!field) continue
    const key = draftKeyFor(item.target, field)
    const existingDraft = drafts.value[key]
    const current = Number(existingDraft?.newValue ?? field.value)
    let next = amount
    if (batchOperation.value === 'add') next = current + amount
    if (batchOperation.value === 'percent') next = current * (1 + amount / 100)
    next = Number(next.toPrecision(12))
    if (!Number.isFinite(next) || next < field.minimum || next > field.maximum) {
      localError.value = `${item.target} 的${field.label}计算后为 ${next}，超出 ${field.minimum}～${field.maximum} ${field.unit}`
      return
    }
    if (next === Number(field.value)) {
      if (existingDraft) updates.push({ key })
    } else if (next !== current) {
      updates.push({
        key,
        draft: {
          key,
          section: field.section,
          target: item.target,
          field: field.field,
          label: field.label,
          unit: field.unit,
          oldValue: field.value,
          newValue: String(next),
        },
      })
    }
  }

  if (!updates.length) {
    localError.value = '计算后的参数没有发生变化'
    return
  }
  const copy = { ...drafts.value }
  updates.forEach(({ key, draft }) => {
    if (draft) copy[key] = draft
    else delete copy[key]
  })
  drafts.value = copy
}

function removeDraft(key: string) {
  const copy = { ...drafts.value }
  delete copy[key]
  drafts.value = copy
}

function clearDrafts() {
  drafts.value = {}
  localError.value = ''
  resetDuration()
  resetReportStep()
}

function resetDuration() {
  durationSeconds.value = store.simulationOptions?.duration_seconds || 0
}

function resetReportStep() {
  reportStepSeconds.value = store.simulationOptions?.report_step_seconds || 0
}

function formatDateTime(value: string) {
  const date = parseSimulationDate(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())}`
}

function parseSimulationDate(value: string) {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`)
}

async function saveVersion() {
  const parentId = store.selectedVersionId
  if (!parentId || simulationError.value) return
  const result = await store.saveAdjustedVersion(
    draftsList.value.map((draft) => ({
      section: draft.section,
      target: draft.target,
      field: draft.field,
      new_value: draft.newValue,
    })),
    summary.value || undefined,
    simulationOptionsChanged.value
      ? {
          duration_seconds: durationSeconds.value,
          report_step_seconds: reportStepSeconds.value,
        }
      : undefined,
  )
  if (!result) return
  createdVersion.value = result.version
  summary.value = ''
  clearDrafts()
}

async function runCreatedVersion() {
  const result = await store.runSelectedVersion()
  if (!result) return
  eventBus.emit('modelRunCompleted', result)
}

async function handleMapSelection(payload: { layerId: string; target: string }) {
  const group = groups.value.find((item) => item.map_layer === payload.layerId)
  if (!group?.objects.some((item) => item.target === payload.target)) return

  const groupChanged = selectedGroupId.value !== group.id
  selectedGroupId.value = group.id
  if (groupChanged) await nextTick()

  if (selectionMode.value === 'batch') {
    if (!selectedTargets.value.includes(payload.target)) {
      selectedTargets.value = [...selectedTargets.value, payload.target]
    }
  } else {
    selectedTarget.value = payload.target
  }
}

onMounted(() => eventBus.on('mapFeatureSelected', handleMapSelection))
onBeforeUnmount(() => eventBus.off('mapFeatureSelected', handleMapSelection))
</script>

<style scoped src="@/assets/css/ParameterTuning.css"></style>
