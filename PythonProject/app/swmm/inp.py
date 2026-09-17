"""Application target-neutral INP context required by downstream result consumers."""

from dataclasses import dataclass
from pathlib import Path

from app.swmm._rpt_parser import (
    OutfallInfo,
    SubcatchmentInfo,
    SwmmInpData,
    _read_text_file,
    _resolve_virtual_outfall_coordinate,
    build_outlet_map,
    load_inp,
    parse_inp_junctions,
    parse_inp_outfalls,
    parse_inp_polygons,
    parse_inp_subcatchments,
)


@dataclass(frozen=True)
class SwmmInpContext:
    """Static model context that an RPT alone cannot provide."""

    path: Path
    info: SwmmInpData
    subcatchments: list[SubcatchmentInfo]
    outfalls: list[OutfallInfo]
    junctions: list[str]
    polygons: dict[str, list[list[float]]]
    outlet_map: dict[str, tuple[str, ...]]


def load_inp_context(inp_path: str | Path) -> SwmmInpContext:
    """Load coordinates, topology and duration from an INP once."""
    path = Path(inp_path).expanduser().resolve()
    text = _read_text_file(path)
    info = load_inp(path)
    subcatchments = parse_inp_subcatchments(text)
    outfalls = parse_inp_outfalls(text)
    junctions = parse_inp_junctions(text)
    polygons = parse_inp_polygons(text)
    node_names = set(junctions) | {item.name for item in outfalls}
    outlet_map, _ = build_outlet_map(subcatchments, node_names)
    return SwmmInpContext(
        path=path,
        info=info,
        subcatchments=subcatchments,
        outfalls=outfalls,
        junctions=junctions,
        polygons=polygons,
        outlet_map=outlet_map,
    )


def resolve_node_coordinate(context: SwmmInpContext, node: str) -> list[float] | None:
    """Return an explicit node coordinate or a subcatchment-centroid fallback."""
    coordinate = context.info.coordinates.get(node)
    if coordinate is not None:
        return coordinate
    coordinate, _ = _resolve_virtual_outfall_coordinate(
        node,
        context.info.coordinates,
        list(context.outlet_map.get(node, ())),
        context.polygons,
    )
    return coordinate
