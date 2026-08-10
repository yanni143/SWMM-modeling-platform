import json
from pathlib import Path
from typing import Any

from pyswmm import LinkSeries, NodeSeries, Output
from swmm.toolkit.shared_enum import SubcatchAttribute

from Tools.InpTools.InpGeoJson import build_geojson_layers
from Tools.InpTools.InpValidator import validate_inp_file
from config import get_settings


def _geometry_index(layers: list[dict], layer_id: str) -> dict[str, dict]:
    layer = next((item for item in layers if item["id"] == layer_id), None)
    if not layer:
        return {}
    return {
        feature["properties"]["name"]: feature["geometry"]
        for feature in layer["geojson"]["features"]
    }


def _value(series: Any, attribute: str, timestamp: Any) -> float | None:
    try:
        value = getattr(series, attribute)[timestamp]
        return float(value) if value is not None else None
    except Exception:
        return None


def _feature(geometry: dict, name: str, time_index: int, **values: Any) -> dict:
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {"name": name, "time": time_index, **values},
    }


def parse_result_layers(inp_path: str | Path, out_path: str | Path) -> list[dict[str, Any]]:
    sections = validate_inp_file(inp_path).sections
    base_layers = build_geojson_layers(
        sections,
        source_crs=get_settings().swmm_input_crs,
    )
    node_geometry = _geometry_index(base_layers, "inp-nodes")
    link_geometry = _geometry_index(base_layers, "inp-conduits")
    sub_geometry = _geometry_index(base_layers, "inp-subcatchments")

    node_features: list[dict] = []
    link_features: list[dict] = []
    sub_features: list[dict] = []
    with Output(str(out_path)) as output:
        times = list(output.times)
        node_series = NodeSeries(output)
        link_series = LinkSeries(output)

        for name, geometry in node_geometry.items():
            if name not in output.nodes:
                continue
            series = node_series[name]
            for index, timestamp in enumerate(times):
                node_features.append(
                    _feature(
                        geometry,
                        name,
                        index,
                        depth=_value(series, "invert_depth", timestamp),
                        head=_value(series, "hydraulic_head", timestamp),
                        ponded_v=_value(series, "ponded_volume", timestamp),
                        lateral_i=_value(series, "lateral_inflow", timestamp),
                        total_i=_value(series, "total_inflow", timestamp),
                        flooding=_value(series, "flooding_losses", timestamp),
                    )
                )

        for name, geometry in link_geometry.items():
            if name not in output.links:
                continue
            series = link_series[name]
            for index, timestamp in enumerate(times):
                link_features.append(
                    _feature(
                        geometry,
                        name,
                        index,
                        rate=_value(series, "flow_rate", timestamp),
                        depth=_value(series, "flow_depth", timestamp),
                        velocity=_value(series, "flow_velocity", timestamp),
                        volume=_value(series, "flow_volume", timestamp),
                        capacity=_value(series, "capacity", timestamp),
                    )
                )

        sub_attributes = {
            "rain": SubcatchAttribute.RAINFALL,
            "snow": SubcatchAttribute.SNOW_DEPTH,
            "evap": SubcatchAttribute.EVAP_LOSS,
            "infilt": SubcatchAttribute.INFIL_LOSS,
            "runoff": SubcatchAttribute.RUNOFF_RATE,
            "gw_flow": SubcatchAttribute.GW_OUTFLOW_RATE,
            "soil_moist": SubcatchAttribute.SOIL_MOISTURE,
        }
        for name, geometry in sub_geometry.items():
            if name not in output.subcatchments:
                continue
            values: dict[str, list[float | None]] = {}
            for field, attribute in sub_attributes.items():
                try:
                    series = output.subcatch_series(name, attribute)
                    values[field] = [float(value) if value is not None else None for value in series.values()]
                except Exception:
                    values[field] = [None] * len(times)
            for index in range(len(times)):
                sub_features.append(
                    _feature(
                        geometry,
                        name,
                        index,
                        **{field: series[index] if index < len(series) else None for field, series in values.items()},
                    )
                )

    definitions = (
        ("result-subcatchments", "子汇水区模拟结果", "fill", sub_features),
        ("result-conduits", "管线模拟结果", "line", link_features),
        ("result-nodes", "节点模拟结果", "circle", node_features),
    )
    return [
        {
            "id": layer_id,
            "name": name,
            "geometry_type": geometry_type,
            "source": "simulation",
            "geojson": {"type": "FeatureCollection", "features": features},
        }
        for layer_id, name, geometry_type, features in definitions
        if features
    ]


def write_result_layers(layers: list[dict], directory: str | Path) -> list[Path]:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    paths = []
    for layer in layers:
        path = target / f"{layer['id']}.geojson"
        path.write_text(json.dumps(layer["geojson"], ensure_ascii=False), encoding="utf-8")
        paths.append(path)
    return paths
