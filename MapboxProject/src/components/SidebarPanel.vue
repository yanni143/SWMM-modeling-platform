<template>
  <div class="sidebar-panel">
    <LayerControl
      :layers="layers"
      :layer-visibility="layerVisibility"
      @layer-visibility-change="(id, visible) => $emit('layer-visibility-change', id, visible)"
    />
  </div>
</template>

<script>
import LayerControl from './LayerControl.vue'

export default {
  name: 'SidebarPanel',
  components: { LayerControl },
  props: {
    layers: { type: Array, required: true },
    layerVisibility: { type: Object, required: true },
  },
  emits: ['layer-visibility-change'],
}
</script>

<style scoped>
.sidebar-panel {
  position: absolute;
  z-index: 3;
  top: 72px;
  left: 16px;
  width: 264px;
}
</style>
