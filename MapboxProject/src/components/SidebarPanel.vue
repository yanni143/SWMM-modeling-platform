<template>
  <div class="sidebar-panel">
    <LayerControl
      :original-data-files="originalDataFiles"
      :simulation-result-files="simulationResultFiles"
      :layer-visibility="layerVisibility"
      @layer-visibility-change="handleLayerVisibilityChange"
    />
  </div>
</template>

<script>
import LayerControl from './LayerControl.vue'

export default {
  name: 'SidebarPanel',
  components: {
    LayerControl,
  },
  props: {
    originalDataFiles: {
      type: Array,
      required: true,
    },
    simulationResultFiles: {
      type: Array,
      required: true,
    },
    layerVisibility: {
      type: Object,
      required: true,
    },
  },
  methods: {
    handleLayerVisibilityChange(layerName, isVisible) {
      this.$emit('layer-visibility-change', layerName, isVisible)
    },
  },
}
</script>

<style scoped>
.sidebar-panel {
  background-color: white;
  position: absolute;
  left: 0px;
  top: 60px;
  width: 250px;
  z-index: 2;
  display: flex;
  flex-direction: column;
  height: auto;
}
</style>
