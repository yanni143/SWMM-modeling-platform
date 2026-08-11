from collections import defaultdict
from collections.abc import Callable
from typing import Any

from pyproj import Transformer

from Tools.InpTools.InpInspector import data_lines, inspect_section


def _properties_by_name(sections: dict[str, list[str]], section: str) -> dict[str, dict]:
    if section not in sections:
        return {}
    details = inspect_section(section, sections[section])
    return {
        record["target"]: {
            key: value for key, value in record["values"].items() if value is not None
        }
        for record in details["records"]
        if record["target"]
    }


def _spatial_reference(sections: dict[str, list[str]]) -> tuple[float, float] | None:
    for section in ("COORDINATES", "POLYGONS", "VERTICES"):
        for line in data_lines(sections.get(section, [])):
            values = line.split()
            if len(values) >= 3:
                try:
                    return float(values[1]), float(values[2])
                except ValueError:
                    continue
    return None


def _coordinate_converter(
    sections: dict[str, list[str]], source_crs: str
) -> tuple[Callable[[float, float], list[float]], bool]:
    reference = _spatial_reference(sections)
    projected = bool(
        reference
        and not (-180 <= reference[0] <= 180 and -90 <= reference[1] <= 90)
    )
    if not projected:
        return lambda x, y: [x, y], False

    transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)

    def convert(x: float, y: float) -> list[float]:
        longitude, latitude = transformer.transform(x, y)
        return [longitude, latitude]

    return convert, True


def build_geojson_layers(
    sections: dict[str, list[str]], source_crs: str = "EPSG:4549"
) -> list[dict[str, Any]]:
    """Build map layers from SWMM spatial sections without relying on SHP files."""
    convert, transformed = _coordinate_converter(sections, source_crs)
    coordinates: dict[str, list[float]] = {}
    for line in data_lines(sections.get("COORDINATES", [])):
        values = line.split()
        if len(values) >= 3:
            try:
                coordinates[values[0]] = convert(float(values[1]), float(values[2]))
            except ValueError:
                continue

    node_properties: dict[str, dict] = {}
    for section in ("JUNCTIONS", "OUTFALLS", "DIVIDERS"):
        for name, properties in _properties_by_name(sections, section).items():
            node_properties[name] = {**properties, "element_type": section.lower()}

    # Some exported INP files also put subcatchment label/centroid coordinates in
    # [COORDINATES]. Keep the complete coordinate index for link endpoints, but
    # only render identifiers that are declared in an actual SWMM node section.
    node_features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": point},
            "properties": {"name": name, **node_properties.get(name, {})},
        }
        for name, point in coordinates.items()
        if name in node_properties
    ]

    vertices: dict[str, list[list[float]]] = defaultdict(list)
    for line in data_lines(sections.get("VERTICES", [])):
        values = line.split()
        if len(values) >= 3:
            try:
                vertices[values[0]].append(convert(float(values[1]), float(values[2])))
            except ValueError:
                continue

    conduit_features = []
    for name, properties in _properties_by_name(sections, "CONDUITS").items():
        start = coordinates.get(properties.get("from_node", ""))
        end = coordinates.get(properties.get("to_node", ""))
        if not start or not end:
            continue
        conduit_features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [start, *vertices.get(name, []), end],
                },
                "properties": {"name": name, **properties},
            }
        )

    polygon_points: dict[str, list[list[float]]] = defaultdict(list)
    for line in data_lines(sections.get("POLYGONS", [])):
        values = line.split()
        if len(values) >= 3:
            try:
                polygon_points[values[0]].append(convert(float(values[1]), float(values[2])))
            except ValueError:
                continue

    subcatchment_properties = _properties_by_name(sections, "SUBCATCHMENTS")
    polygon_features = []
    for name, points in polygon_points.items():
        if len(points) < 3:
            continue
        ring = points if points[0] == points[-1] else [*points, points[0]]
        polygon_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {"name": name, **subcatchment_properties.get(name, {})},
            }
        )

    definitions = (
        ("inp-subcatchments", "子汇水区", "fill", polygon_features),
        ("inp-conduits", "管线", "line", conduit_features),
        ("inp-nodes", "节点", "circle", node_features),
    )
    return [
        {
            "id": layer_id,
            "name": name,
            "geometry_type": geometry_type,
            "source": "inp",
            "source_crs": source_crs if transformed else "EPSG:4326",
            "display_crs": "EPSG:4326",
            "geojson": {"type": "FeatureCollection", "features": features},
        }
        for layer_id, name, geometry_type, features in definitions
        if features
    ]
