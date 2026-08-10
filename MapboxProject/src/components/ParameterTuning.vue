<template>
  <section class="tuning-workspace" aria-label="参数调整">
    <div class="tuning-heading">
      <div>
        <small>SAFE PARAMETER SET</small>
        <h3>常用参数调整</h3>
      </div>
      <span>{{ draftsList.length }} 项待保存</span>
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
          <small>BATCH OPERATION</small>
          <strong>已选择 {{ selectedTargets.length }} 个{{ activeGroup?.label }}</strong>
        </div>
        <span>{{ filteredSelectedCount }} 个在当前搜索结果中</span>
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

    <p v-if="localError" class="tuning-error" role="alert">{{ localError }}</p>

    <div v-if="draftsList.length" class="change-ruler">
      <div class="change-ruler-title">
        <span>变更预览</span>
        <button type="button" @click="clearDrafts">全部撤销</button>
      </div>
      <div v-for="draft in draftsList" :key="draft.key" class="change-line">
        <span>{{ draft.target }} · {{ draft.label }}</span>
        <code>{{ draft.oldValue }}</code>
        <i>→</i>
        <code>{{ draft.newValue }} {{ draft.unit }}</code>
        <button type="button" aria-label="撤销该项" @click="removeDraft(draft.key)">×</button>
      </div>
      <input v-model.trim="summary" maxlength="500" placeholder="版本说明，例如：降低管线粗糙度" />
      <button class="save-version" type="button" :disabled="store.savingVersion" @click="saveVersion">
        {{ store.savingVersion ? '正在校验并生成…' : `校验并生成 V${nextVersionNumber}` }}
      </button>
    </div>

    <div v-if="createdVersion" class="version-created">
      <div>
        <small>NEW VERSION</small>
        <strong>V{{ createdVersion.version }} 已生成</strong>
        <span>原版本未被覆盖</span>
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
const nextVersionNumber = computed(() => Math.max(...store.versions.map((item) => item.version), 0) + 1)

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
}

async function saveVersion() {
  const parentId = store.selectedVersionId
  if (!parentId) return
  const result = await store.saveAdjustedVersion(
    draftsList.value.map((draft) => ({
      section: draft.section,
      target: draft.target,
      field: draft.field,
      new_value: draft.newValue,
    })),
    summary.value || undefined,
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
