"""Convert SWMM flooding and outfall volumes into LISFLOOD point sources."""

import json
from collections import OrderedDict
from pathlib import Path

from app.lisflood_coupling.input import LisfloodInput
from app.swmm.inp import load_inp_context, resolve_node_coordinate
from app.swmm.rpt import parse_report_flows

_M3_PER_1E6_LITRE = 1000.0
_SECONDS_PER_HOUR = 3600.0
_RATE_DECIMALS = 6


def _is_system_row(node: str) -> bool:
    return node.strip().lower() == "system"


def build_point_flooding(coupling_input: LisfloodInput) -> list[dict[str, object]]:
    """Build the legacy-compatible ``rate`` rows without surface storage.

    The point-selection policy is intentionally owned here, rather than in the
    generic SWMM parser: LISFLOOD accepts virtual subcatchment outlets and
    flooded nodes, but excludes unassigned real outfalls.
    """
    source = coupling_input.normalized()
    context = load_inp_context(source.inp_path)
    report = parse_report_flows(source.rpt_path)

    designated = set(context.outlet_map)
    virtual_by_name = [item.name for item in context.outfalls if item.is_virtual]
    virtual_names = designated | set(virtual_by_name)
    real_outfalls = {item.name for item in context.outfalls if not item.is_virtual}

    candidates: OrderedDict[str, None] = OrderedDict()
    for node in context.outlet_map:
        candidates.setdefault(node, None)
    for node in virtual_by_name:
        candidates.setdefault(node, None)
    for item in report.node_flooding:
        candidates.setdefault(item.node, None)
    for item in report.outfall_flows:
        if not _is_system_row(item.node) and item.node in real_outfalls and item.node not in virtual_names:
            candidates.pop(item.node, None)

    volume_by_node: dict[str, float] = {}
    for item in report.outfall_flows:
        if not _is_system_row(item.node):
            volume_by_node[item.node] = volume_by_node.get(item.node, 0.0) + (
                item.total_volume * _M3_PER_1E6_LITRE
            )
    for item in report.node_flooding:
        if not _is_system_row(item.node):
            volume_by_node[item.node] = volume_by_node.get(item.node, 0.0) + (
                item.total_flood_volume * _M3_PER_1E6_LITRE
            )

    seconds = context.info.sim_hours * _SECONDS_PER_HOUR
    return [
        {
            "node": node,
            "rate": round(volume_by_node.get(node, 0.0) / seconds, _RATE_DECIMALS),
            "coordinate": resolve_node_coordinate(context, node),
        }
        for node in candidates
    ]


def write_point_flooding(rows: list[dict[str, object]], output_path: str | Path) -> Path:
    """Write the stable API payload consumed by existing LISFLOOD clients."""
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rate": rows}, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    return path
