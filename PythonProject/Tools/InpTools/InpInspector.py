from typing import Any


SECTION_FIELDS: dict[str, list[str]] = {
    "OPTIONS": ["option", "value"],
    "EVAPORATION": ["format", "value"],
    "RAINGAGES": ["name", "format", "interval", "scf", "source", "series"],
    "SUBCATCHMENTS": [
        "name", "raingage", "outlet", "area", "imperv", "width", "slope",
        "curb_length", "snowpack",
    ],
    "SUBAREAS": [
        "name", "n_imperv", "n_perv", "s_imperv", "s_perv", "pct_zero", "route_to",
        "pct_routed",
    ],
    "INFILTRATION": ["name", "param1", "param2", "param3", "param4", "param5"],
    "JUNCTIONS": ["name", "elevation", "max_depth", "init_depth", "surcharge_depth", "ponded_area"],
    "OUTFALLS": ["name", "elevation", "type", "stage_data", "gated", "route_to"],
    "STORAGE": [
        "name", "elevation", "max_depth", "init_depth", "shape", "curve_or_coefficient",
        "exponent", "constant", "ponded_area", "evap_factor",
    ],
    "CONDUITS": [
        "name", "from_node", "to_node", "length", "roughness", "in_offset", "out_offset",
        "init_flow", "max_flow",
    ],
    "XSECTIONS": ["link", "shape", "geom1", "geom2", "geom3", "geom4", "barrels", "culvert"],
    "LOSSES": ["link", "inlet", "outlet", "average", "flap_gate", "seepage"],
    "TIMESERIES": ["name", "date", "time", "value"],
    "REPORT": ["option", "value"],
    "TAGS": ["object_type", "object_name", "tag"],
    "MAP": ["option", "value1", "value2", "value3", "value4"],
    "COORDINATES": ["node", "x", "y"],
    "VERTICES": ["link", "x", "y"],
    "POLYGONS": ["subcatchment", "x", "y"],
    "SYMBOLS": ["gage", "x", "y"],
}


EDITABLE_SECTIONS = {
    "OPTIONS",
    "EVAPORATION",
    "RAINGAGES",
    "SUBCATCHMENTS",
    "SUBAREAS",
    "INFILTRATION",
    "JUNCTIONS",
    "OUTFALLS",
    "STORAGE",
    "CONDUITS",
    "XSECTIONS",
    "LOSSES",
    "TIMESERIES",
}


def data_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if line.strip() and not line.lstrip().startswith(";")]


def summarize_sections(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "record_count": len(data_lines(lines)),
            "editable": name in EDITABLE_SECTIONS,
            "fields": SECTION_FIELDS.get(name, []),
        }
        for name, lines in sections.items()
    ]


def inspect_section(section: str, lines: list[str]) -> dict[str, Any]:
    section_name = section.upper()
    fields = SECTION_FIELDS.get(section_name, [])
    records = []

    for index, line in enumerate(data_lines(lines)):
        values = line.split()
        record = {
            "index": index,
            "target": values[0] if values else None,
            "values": {
                field: values[position] if position < len(values) else None
                for position, field in enumerate(fields)
            },
            "extra_values": values[len(fields):] if fields else values,
            "raw": line,
        }
        records.append(record)

    return {
        "name": section_name,
        "editable": section_name in EDITABLE_SECTIONS,
        "fields": fields,
        "record_count": len(records),
        "records": records,
    }
