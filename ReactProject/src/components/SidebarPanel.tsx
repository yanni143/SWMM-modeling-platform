import type { ResultTimeline, SimulationTimelineStep } from '@/api/models';
import '@/assets/css/SidebarPanel.css';
import LayerControl, { type LayerDescriptor } from './LayerControl';
import SimulationTimeline from './SimulationTimeline';
export default function SidebarPanel(props: {
  layers: LayerDescriptor[];
  visibility: Record<string, boolean>;
  steps: SimulationTimelineStep[];
  activeTimeIndex: number;
  ranges: ResultTimeline['result_ranges'];
  metadata: ResultTimeline['result_metadata'];
  playing: boolean;
  loading: boolean;
  onVisibilityChange: (id: string, value: boolean) => void;
  onOrderChange: (change: {
    draggedId: string;
    targetId: string;
    position: 'before' | 'after';
  }) => void;
  onTimeChange: (time: number) => void;
  onToggle: () => void;
}) {
  return (
    <div className="sidebar-panel">
      <LayerControl
        layers={props.layers}
        visibility={props.visibility}
        onVisibilityChange={props.onVisibilityChange}
        onOrderChange={props.onOrderChange}
      />
      {props.steps.length > 0 && (
        <SimulationTimeline
          steps={props.steps}
          activeTimeIndex={props.activeTimeIndex}
          ranges={props.ranges}
          metadata={props.metadata}
          playing={props.playing}
          loading={props.loading}
          onTimeChange={props.onTimeChange}
          onToggle={props.onToggle}
        />
      )}
    </div>
  );
}
