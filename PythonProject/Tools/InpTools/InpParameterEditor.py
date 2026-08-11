import math
from dataclasses import dataclass
from typing import Any

from Tools.InpTools.InpInspector import SECTION_FIELDS, inspect_section


class ParameterValidationError(ValueError):
    pass


@dataclass(frozen=True)
class FieldSpec:
    section: str
    field: str
    label: str
    unit: str
    minimum: float
    maximum: float
    step: float

    @property
    def key(self) -> str:
        return f"{self.section}.{self.field}"


GROUPS = {
    "subcatchments": {
        "label": "子汇水区",
        "map_layer": "inp-subcatchments",
        "sections": ("SUBCATCHMENTS", "SUBAREAS", "INFILTRATION"),
    },
    "nodes": {
        "label": "节点与排口",
        "map_layer": "inp-nodes",
        "sections": ("JUNCTIONS", "OUTFALLS"),
    },
    "conduits": {
        "label": "管线",
        "map_layer": "inp-conduits",
        "sections": ("CONDUITS", "XSECTIONS"),
    },
}


FIELD_SPECS = {
    "SUBCATCHMENTS.area": FieldSpec("SUBCATCHMENTS", "area", "面积", "ha", 0.0001, 1_000_000, 0.01),
    "SUBCATCHMENTS.imperv": FieldSpec("SUBCATCHMENTS", "imperv", "不透水率", "%", 0, 100, 0.1),
    "SUBCATCHMENTS.width": FieldSpec(
        "SUBCATCHMENTS", "width", "特征宽度", "m", 0.0001, 1_000_000, 0.1
    ),
    "SUBCATCHMENTS.slope": FieldSpec("SUBCATCHMENTS", "slope", "平均坡度", "%", 0, 100, 0.01),
    "SUBAREAS.n_imperv": FieldSpec("SUBAREAS", "n_imperv", "不透水区曼宁系数", "", 0.001, 1, 0.001),
    "SUBAREAS.n_perv": FieldSpec("SUBAREAS", "n_perv", "透水区曼宁系数", "", 0.001, 1, 0.001),
    "SUBAREAS.s_imperv": FieldSpec("SUBAREAS", "s_imperv", "不透水区洼蓄量", "mm", 0, 1000, 0.1),
    "SUBAREAS.s_perv": FieldSpec("SUBAREAS", "s_perv", "透水区洼蓄量", "mm", 0, 1000, 0.1),
    "SUBAREAS.pct_zero": FieldSpec("SUBAREAS", "pct_zero", "零洼蓄不透水区比例", "%", 0, 100, 0.1),
    "INFILTRATION.param1": FieldSpec("INFILTRATION", "param1", "下渗参数 1", "", 0, 100000, 0.1),
    "INFILTRATION.param2": FieldSpec("INFILTRATION", "param2", "下渗参数 2", "", 0, 100000, 0.1),
    "INFILTRATION.param3": FieldSpec("INFILTRATION", "param3", "下渗参数 3", "", 0, 100000, 0.1),
    "INFILTRATION.param4": FieldSpec("INFILTRATION", "param4", "下渗参数 4", "", 0, 100000, 0.1),
    "INFILTRATION.param5": FieldSpec("INFILTRATION", "param5", "下渗参数 5", "", 0, 100000, 0.1),
    "JUNCTIONS.elevation": FieldSpec(
        "JUNCTIONS", "elevation", "底部高程", "m", -10000, 10000, 0.01
    ),
    "JUNCTIONS.max_depth": FieldSpec(
        "JUNCTIONS", "max_depth", "最大深度", "m", 0.0001, 10000, 0.01
    ),
    "OUTFALLS.elevation": FieldSpec("OUTFALLS", "elevation", "排口高程", "m", -10000, 10000, 0.01),
    "CONDUITS.length": FieldSpec("CONDUITS", "length", "管线长度", "m", 0.0001, 10_000_000, 0.1),
    "CONDUITS.roughness": FieldSpec("CONDUITS", "roughness", "粗糙度", "", 0.0001, 1, 0.001),
    "XSECTIONS.geom1": FieldSpec("XSECTIONS", "geom1", "圆管管径", "m", 0.0001, 1000, 0.01),
}


INFILTRATION_LABELS = {
    "HORTON": ("最大下渗率", "最小下渗率", "衰减系数", "干燥时间", "最大下渗体积"),
    "MODIFIED_HORTON": ("最大下渗率", "最小下渗率", "衰减系数", "干燥时间", "最大下渗体积"),
    "GREEN_AMPT": ("毛细吸力", "饱和导水率", "初始含水量亏缺", "", ""),
    "MODIFIED_GREEN_AMPT": ("毛细吸力", "饱和导水率", "初始含水量亏缺", "", ""),
    "CURVE_NUMBER": ("曲线数 CN", "饱和导水率", "干燥时间", "", ""),
}


def _infiltration_method(sections: dict[str, list[str]]) -> str:
    for record in inspect_section("OPTIONS", sections.get("OPTIONS", []))["records"]:
        if record["target"] == "INFILTRATION":
            return (record["values"].get("value") or "").upper()
    return ""


def _field_payload(spec: FieldSpec, value: str, method: str) -> dict[str, Any] | None:
    label = spec.label
    if spec.section == "INFILTRATION":
        position = int(spec.field.removeprefix("param")) - 1
        labels = INFILTRATION_LABELS.get(method)
        if labels:
            label = labels[position]
            if not label:
                return None
    return {
        "key": spec.key,
        "section": spec.section,
        "field": spec.field,
        "label": label,
        "unit": spec.unit,
        "value": value,
        "minimum": spec.minimum,
        "maximum": spec.maximum,
        "step": spec.step,
    }


def build_parameter_catalog(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    method = _infiltration_method(sections)
    records_by_section = {
        section: inspect_section(section, lines)["records"]
        for section, lines in sections.items()
        if section in SECTION_FIELDS
    }
    groups = []
    for group_id, group in GROUPS.items():
        objects: dict[str, dict] = {}
        for section in group["sections"]:
            for record in records_by_section.get(section, []):
                target = record["target"]
                if not target:
                    continue
                if (
                    section == "XSECTIONS"
                    and record["values"].get("shape", "").upper() != "CIRCULAR"
                ):
                    continue
                item = objects.setdefault(
                    target,
                    {"target": target, "element_type": section.lower(), "fields": []},
                )
                for field, value in record["values"].items():
                    spec = FIELD_SPECS.get(f"{section}.{field}")
                    if spec and value is not None:
                        payload = _field_payload(spec, value, method)
                        if payload:
                            item["fields"].append(payload)
        visible = [item for item in objects.values() if item["fields"]]
        if visible:
            groups.append(
                {
                    "id": group_id,
                    "label": group["label"],
                    "map_layer": group["map_layer"],
                    "objects": visible,
                }
            )
    return groups


def validate_change(section: str, target: str, field: str, new_value: str) -> tuple[FieldSpec, str]:
    key = f"{section.upper()}.{field}"
    spec = FIELD_SPECS.get(key)
    if not spec:
        raise ParameterValidationError(f"不支持修改参数：{key}")
    try:
        number = float(new_value)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError(f"{spec.label}必须是数字") from exc
    if not math.isfinite(number):
        raise ParameterValidationError(f"{spec.label}必须是有限数字")
    if number < spec.minimum or number > spec.maximum:
        raise ParameterValidationError(
            f"{spec.label}必须在 {spec.minimum:g}～{spec.maximum:g} {spec.unit} 之间"
        )
    normalized = f"{number:.12g}"
    return spec, normalized


def apply_parameter_changes(content: str, changes: list[dict[str, str]]) -> tuple[str, list[dict]]:
    pending: dict[tuple[str, str, str], tuple[FieldSpec, str]] = {}
    for change in changes:
        section = change["section"].upper()
        target = change["target"]
        field = change["field"]
        spec, normalized = validate_change(section, target, field, change["new_value"])
        pending[(section, target, field)] = (spec, normalized)

    current_section = ""
    applied: list[dict] = []
    output = []
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].upper()
            output.append(line)
            continue
        if not stripped or stripped.startswith(";"):
            output.append(line)
            continue

        tokens = stripped.split()
        target = tokens[0] if tokens else ""
        changed = False
        for (section, wanted_target, field), (spec, new_value) in list(pending.items()):
            if current_section != section or target != wanted_target:
                continue
            fields = SECTION_FIELDS[section]
            position = fields.index(field)
            if position >= len(tokens):
                raise ParameterValidationError(f"{section}.{field} 在对象 {target} 中缺少原始值")
            if section == "XSECTIONS" and tokens[1].upper() != "CIRCULAR":
                raise ParameterValidationError(f"仅支持修改圆管 {target} 的管径")
            old_value = tokens[position]
            tokens[position] = new_value
            applied.append(
                {
                    "operation": "set",
                    "section": section,
                    "target": target,
                    "field": field,
                    "old_value": old_value,
                    "new_value": new_value,
                    "label": spec.label,
                    "unit": spec.unit,
                }
            )
            del pending[(section, wanted_target, field)]
            changed = True
        output.append(
            (" ".join(tokens) + ("\n" if line.endswith(("\n", "\r")) else "")) if changed else line
        )

    if pending:
        missing = ", ".join(f"{section}/{target}/{field}" for section, target, field in pending)
        raise ParameterValidationError(f"未找到待修改对象：{missing}")
    if not applied:
        raise ParameterValidationError("没有有效的参数修改")
    return "".join(output), applied
