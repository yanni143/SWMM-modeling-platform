<template>
  <div class="sidebar-panel">
    <LayerControl
      :layers="layers"
      :layer-visibility="layerVisibility"
      @layer-visibility-change="(id, visible) => $emit('layer-visibility-change', id, visible)"
      @layer-order-change="(change) => $emit('layer-order-change', change)"
    />
    <SimulationTimeline
      v-if="timelineSteps.length"
      :steps="timelineSteps"
      :active-time-index="activeTimeIndex"
      :result-ranges="resultRanges"
      :result-metadata="resultMetadata"
      :playing="timelinePlaying"
      :loading="timelineLoading"
      @time-change="(timeIndex) => $emit('time-change', timeIndex)"
      @toggle-playback="$emit('toggle-playback')"
    />
  </div>
</template>

<script>
import LayerControl from './LayerControl.vue'
import SimulationTimeline from './SimulationTimeline.vue'

export default {
  name: 'SidebarPanel',
  components: { LayerControl, SimulationTimeline },
  props: {
    layers: { type: Array, required: true },
    layerVisibility: { type: Object, required: true },
    timelineSteps: { type: Array, required: true },
    activeTimeIndex: { type: Number, required: true },
    resultRanges: { type: Object, required: true },
    resultMetadata: { type: Object, required: true },
    timelinePlaying: { type: Boolean, default: false },
    timelineLoading: { type: Boolean, default: false },
  },
  emits: ['layer-visibility-change', 'layer-order-change', 'time-change', 'toggle-playback'],
}
</script>

<style scoped>
.sidebar-panel {
  position: absolute;
  z-index: 3;
  top: 72px;
  left: 16px;
  width: 264px;
  display: grid;
  gap: 12px;
}
</style>
