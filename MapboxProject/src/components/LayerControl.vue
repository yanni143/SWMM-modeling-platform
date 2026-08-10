<template>
  <section class="layer-control" :class="{ collapsed: isCollapsed }" aria-label="工程图层">
    <button class="layer-top" type="button" :aria-expanded="!isCollapsed" @click="toggleCollapse">
      <span>
        <small>MAP CONTENT</small>
        工程图层
      </span>
      <b>{{ layers.length }}</b>
      <i aria-hidden="true">{{ isCollapsed ? '+' : '−' }}</i>
    </button>

    <div v-show="!isCollapsed" class="layer-list">
      <label v-for="layer in layers" :key="layer.id" class="layer-item">
        <input
          type="checkbox"
          :checked="layerVisibility[layer.id]"
          @change="handleLayerChange(layer.id, $event)"
        />
        <span class="layer-swatch" :data-geometry="layer.type"></span>
        <span class="layer-name">{{ layer.displayName || layer.name }}</span>
        <small>{{ layer.source === 'inp' ? 'INP' : 'RUN' }}</small>
      </label>

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
  data: () => ({ isCollapsed: false }),
  methods: {
    handleLayerChange(layerId, event) {
      this.$emit('layer-visibility-change', layerId, event.target.checked)
    },
    toggleCollapse() {
      this.isCollapsed = !this.isCollapsed
    },
  },
}
</script>
