<template>
  <section class="layer-control" :class="{ collapsed: isCollapsed }" aria-label="工程图层">
    <button class="layer-top" type="button" :aria-expanded="!isCollapsed" @click="toggleCollapse">
      <span>图层管理</span>
      <i aria-hidden="true">{{ isCollapsed ? '+' : '−' }}</i>
    </button>

    <div v-show="!isCollapsed" class="layer-list">
      <div
        v-for="layer in layers"
        :key="layer.id"
        class="layer-item"
        :class="{
          dragging: draggedLayerId === layer.id,
          'drop-before': dragOverLayerId === layer.id && dropPosition === 'before',
          'drop-after': dragOverLayerId === layer.id && dropPosition === 'after',
        }"
        @dragover.prevent="handleDragOver(layer.id, $event)"
        @drop.prevent="handleDrop(layer.id)"
      >
        <span
          class="drag-handle"
          draggable="true"
          tabindex="0"
          role="button"
          :aria-label="`拖动${layer.displayName || layer.name}调整压盖顺序`"
          title="拖动调整图层压盖顺序"
          @dragstart="handleDragStart(layer.id, $event)"
          @dragend="resetDragState"
          @keydown.up.prevent="moveLayerByKeyboard(layer.id, -1)"
          @keydown.down.prevent="moveLayerByKeyboard(layer.id, 1)"
        >⠿</span>
        <input
          type="checkbox"
          :checked="layerVisibility[layer.id]"
          :aria-label="`${layer.displayName || layer.name}可见性`"
          @change="handleLayerChange(layer.id, $event)"
        />
        <span class="layer-swatch" :data-geometry="layer.type"></span>
        <span class="layer-name">{{ layer.displayName || layer.name }}</span>
        <small>{{ layer.source === 'inp' ? 'INP' : `V${layer.version ?? '—'}·RUN` }}</small>
      </div>

      <div v-if="layers.length === 0" class="no-layers">
        <span aria-hidden="true">⌁</span>
        <strong>地图中还没有工程图层</strong>
        <p>正在加载内置研究区图层，或尚未完成一次模型运行。</p>
      </div>
    </div>
  </section>
</template>

<script>
import '@/assets/css/LayerControl.css'

export default {
  name: 'LayerControl',
  props: {
    layers: { type: Array, required: true },
    layerVisibility: { type: Object, required: true },
  },
  emits: ['layer-visibility-change', 'layer-order-change'],
  data: () => ({
    isCollapsed: false,
    draggedLayerId: null,
    dragOverLayerId: null,
    dropPosition: null,
  }),
  methods: {
    handleLayerChange(layerId, event) {
      this.$emit('layer-visibility-change', layerId, event.target.checked)
    },
    toggleCollapse() {
      this.isCollapsed = !this.isCollapsed
    },
    handleDragStart(layerId, event) {
      this.draggedLayerId = layerId
      event.dataTransfer.effectAllowed = 'move'
      event.dataTransfer.setData('text/plain', layerId)
    },
    handleDragOver(layerId, event) {
      if (!this.draggedLayerId || this.draggedLayerId === layerId) {
        this.dragOverLayerId = null
        this.dropPosition = null
        return
      }
      const bounds = event.currentTarget.getBoundingClientRect()
      this.dragOverLayerId = layerId
      this.dropPosition = event.clientY < bounds.top + bounds.height / 2 ? 'before' : 'after'
      event.dataTransfer.dropEffect = 'move'
    },
    handleDrop(targetId) {
      if (this.draggedLayerId && this.dragOverLayerId === targetId && this.dropPosition) {
        this.$emit('layer-order-change', {
          draggedId: this.draggedLayerId,
          targetId,
          position: this.dropPosition,
        })
      }
      this.resetDragState()
    },
    moveLayerByKeyboard(layerId, offset) {
      const currentIndex = this.layers.findIndex((layer) => layer.id === layerId)
      const target = this.layers[currentIndex + offset]
      if (!target) return
      this.$emit('layer-order-change', {
        draggedId: layerId,
        targetId: target.id,
        position: offset < 0 ? 'before' : 'after',
      })
    },
    resetDragState() {
      this.draggedLayerId = null
      this.dragOverLayerId = null
      this.dropPosition = null
    },
  },
}
</script>
