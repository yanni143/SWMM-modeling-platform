<template>
  <section class="result-presentation" :class="{ collapsed: isCollapsed }" aria-label="结果演示">
    <button
      class="result-top"
      type="button"
      :aria-expanded="!isCollapsed"
      @click="isCollapsed = !isCollapsed"
    >
      <span>结果演示</span>
      <i aria-hidden="true">{{ isCollapsed ? '+' : '−' }}</i>
    </button>

    <div v-show="!isCollapsed" class="result-content">
      <aside class="depth-legends" aria-label="水深图例">
        <div v-for="legend in legends" :key="legend.id" class="depth-legend">
          <strong>{{ legend.label }}</strong>
          <i aria-hidden="true"></i>
          <div class="legend-values">
            <span>0</span>
            <span>{{ formatDepth(legend.maximum) }}</span>
          </div>
        </div>
      </aside>

      <div class="simulation-timeline" aria-label="模拟结果时间轴">
        <div class="timeline-header">
          <button
            class="play-button"
            type="button"
            :aria-label="playing ? '暂停动画' : '播放动画'"
            @click="$emit('toggle-playback')"
          >
            {{ playing ? 'Ⅱ' : '▶' }}
          </button>
          <div class="current-time">
            <strong>{{ formattedTimestamp }}</strong>
          </div>
          <span
            class="loading-spinner"
            :class="{ active: loading }"
            role="status"
            :aria-label="loading ? '正在读取时间步' : undefined"
            :aria-hidden="loading ? undefined : 'true'"
          ></span>
          <span class="step-count">{{ currentPosition + 1 }}/{{ steps.length }}</span>
        </div>

        <input
          class="timeline-range"
          type="range"
          min="0"
          :max="Math.max(steps.length - 1, 0)"
          step="1"
          :value="displayPosition"
          :disabled="steps.length < 2"
          aria-label="选择模拟时间步"
          @input="handleInput"
          @keydown.left.prevent="move(-1)"
          @keydown.right.prevent="move(1)"
        />

        <div class="timeline-endpoints">
          <span>{{ formatTimestamp(steps[0]?.timestamp, true) }}</span>
          <span>{{ formatTimestamp(steps[steps.length - 1]?.timestamp, true) }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script>
export default {
  name: 'SimulationTimeline',
  data: () => ({ isCollapsed: false, previewPosition: null }),
  props: {
    steps: { type: Array, required: true },
    activeTimeIndex: { type: Number, required: true },
    maxDepths: { type: Object, required: true },
    playing: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
  },
  emits: ['time-change', 'toggle-playback'],
  computed: {
    currentPosition() {
      const position = this.steps.findIndex((step) => step.time_index === this.activeTimeIndex)
      return Math.max(position, 0)
    },
    displayPosition() {
      return this.previewPosition ?? this.currentPosition
    },
    formattedTimestamp() {
      return this.formatTimestamp(this.steps[this.displayPosition]?.timestamp)
    },
    legends() {
      return [
        { id: 'nodes', label: '节点水深', maximum: this.maxDepths['result-nodes'] || 0 },
        { id: 'conduits', label: '管线水深', maximum: this.maxDepths['result-conduits'] || 0 },
      ]
    },
  },
  methods: {
    handleInput(event) {
      const position = Number(event.target.value)
      this.previewPosition = position
      const step = this.steps[position]
      if (step) this.$emit('time-change', step.time_index)
    },
    move(offset) {
      const next = Math.min(Math.max(this.displayPosition + offset, 0), this.steps.length - 1)
      this.previewPosition = next
      const step = this.steps[next]
      if (step) this.$emit('time-change', step.time_index)
    },
    formatTimestamp(timestamp, compact = false) {
      if (!timestamp) return '—'
      const [date, time = ''] = timestamp.split('T')
      const clock = time.slice(0, 8)
      return compact ? `${date.slice(5)} ${clock.slice(0, 5)}` : `${date} ${clock}`
    },
    formatDepth(value) {
      if (!Number.isFinite(value)) return '—'
      return `${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
    },
  },
  watch: {
    activeTimeIndex() {
      this.previewPosition = null
    },
  },
}
</script>

<style scoped>
.result-presentation {
  overflow: hidden;
  color: #102a37;
  border: 1px solid rgba(255, 255, 255, 0.78);
  background: rgba(243, 246, 243, 0.95);
  box-shadow: 0 14px 40px rgba(16, 42, 55, 0.18);
  backdrop-filter: blur(10px);
  font-family: Bahnschrift, 'Segoe UI', sans-serif;
}

.result-top {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
  align-items: center;
  width: 100%;
  padding: 13px 15px;
  text-align: left;
  color: #fff;
  border: 0;
  background: #102a37;
  cursor: pointer;
}
.result-top span {
  font-size: 16px;
  font-weight: 650;
}
.result-top i {
  font-size: 16px;
  font-style: normal;
  font-weight: 300;
}
.result-top:hover {
  background: #173b4b;
}
.result-top:focus-visible {
  outline: 2px solid #68c4ce;
  outline-offset: -3px;
}
.result-content {
  padding: 13px 14px 14px;
}
.simulation-timeline {
  padding-top: 13px;
  border-top: 1px solid rgba(16, 42, 55, 0.12);
}

.timeline-header {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) 14px auto;
  gap: 9px;
  align-items: center;
}
.play-button {
  width: 30px;
  height: 30px;
  padding: 0;
  color: #fff;
  border: 0;
  border-radius: 50%;
  background: #102a37;
  cursor: pointer;
}
.play-button:hover,
.play-button:focus-visible {
  background: #23748c;
  outline: 2px solid #68c4ce;
  outline-offset: 2px;
}
.current-time {
  display: flex;
  gap: 10px;
  align-items: baseline;
  min-width: 0;
}
.current-time small {
  color: #63757c;
  font-size: 12px;
  letter-spacing: 0.08em;
}
.current-time strong {
  overflow: hidden;
  font:
    400 13px Consolas,
    monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.step-count {
  color: #23748c;
  font:
    12px Consolas,
    monospace;
}
.loading-spinner {
  width: 12px;
  height: 12px;
  box-sizing: border-box;
  border: 2px solid rgba(35, 116, 140, 0.22);
  border-top-color: #23748c;
  border-radius: 50%;
  visibility: hidden;
}
.loading-spinner.active {
  visibility: visible;
  animation: timeline-spin 0.7s linear infinite;
}

.timeline-range {
  width: 100%;
  height: 18px;
  margin: 8px 0 0;
  accent-color: #23748c;
  cursor: ew-resize;
}
.timeline-range:disabled {
  cursor: default;
  opacity: 0.58;
}
.timeline-endpoints {
  display: flex;
  justify-content: space-between;
  color: #63757c;
  font:
    12px Consolas,
    monospace;
}
@keyframes timeline-spin {
  to {
    transform: rotate(360deg);
  }
}

.depth-legends {
  display: grid;
  gap: 14px;
  padding-bottom: 13px;
}
.depth-legend {
  display: grid;
  gap: 6px;
}
.depth-legend strong {
  font-size: 14px;
  font-weight: 400;
}
.depth-legend i {
  display: block;
  width: 100%;
  height: 8px;
  background: linear-gradient(90deg, #eaf6f8, #9ddce5, #318eae, #083f66);
}
.legend-values {
  display: flex;
  justify-content: space-between;
  color: #586b72;
  font:
    12px Consolas,
    monospace;
  font-variant-numeric: tabular-nums;
}
.legend-values span {
  display: flex;
  gap: 5px;
  align-items: baseline;
}
.legend-values small {
  color: #879397;
  font:
    9px Bahnschrift,
    'Segoe UI',
    sans-serif;
}

@media (max-width: 760px) {
  .result-presentation {
    max-width: calc(100vw - 32px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .play-button {
    transition: none;
  }
  .loading-spinner.active {
    animation-duration: 1.4s;
  }
}
</style>
