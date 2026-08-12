import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from Tools.InpTools.InpInspector import SECTION_FIELDS, inspect_section


class ParameterValidationError(ValueError):
    pass


OPTION_LABELS = {
    "END_DATE": "模拟结束日期",
    "END_TIME": "模拟结束时间",
    "REPORT_STEP": "输出步长",
}


def _option_values(sections: dict[str, list[str]]) -> dict[str, str]:
    return {
        record["target"]: record["values"].get("value") or ""
        for record in inspect_section("OPTIONS", sections.get("OPTIONS", []))["records"]
        if record["target"]
    }


def _parse_datetime(date_value: str, time_value: str, label: str) -> datetime:
    try:
        # SWMM INP dates are deliberately timezone-free model time.
        return datetime.strptime(  # noqa: DTZ007
            f"{date_value} {time_value}", "%m/%d/%Y %H:%M:%S"
        )
    except ValueError as exc:
        raise ParameterValidationError(f"{label}格式无效：{date_value} {time_value}") from exc


def _parse_step_seconds(value: str, label: str, allow_decimal: bool = False) -> float:
    if allow_decimal:
        try:
            seconds = float(value)
        except ValueError:
            pass
        else:
            if math.isfinite(seconds) and seconds > 0:
                return seconds
    parts = value.split(":")
    if len(parts) != 3:
        raise ParameterValidationError(f"{label}格式无效：{value}")
    try:
        hours, minutes, seconds = (int(part) for part in parts)
    except ValueError as exc:
        raise ParameterValidationError(f"{label}格式无效：{value}") from exc
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ParameterValidationError(f"{label}格式无效：{value}")
    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise ParameterValidationError(f"{label}必须大于 0 秒")
    return float(total)


def _format_step(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def build_simulation_options(sections: dict[str, list[str]], settings: Any) -> dict[str, Any]:
    options = _option_values(sections)
    start = _parse_datetime(options.get("START_DATE", ""), options.get("START_TIME", ""), "模拟开始时间")
    end = _parse_datetime(options.get("END_DATE", ""), options.get("END_TIME", ""), "模拟结束时间")
    report_start = _parse_datetime(
        options.get("REPORT_START_DATE", ""), options.get("REPORT_START_TIME", ""), "输出开始时间"
    )
    if report_start != start:
        raise ParameterValidationError("当前模型的输出开始时间必须与模拟开始时间一致")
    duration = int((end - start).total_seconds())
    if duration <= 0:
        raise ParameterValidationError("当前模型的模拟结束时间必须晚于开始时间")
    report_step = int(_parse_step_seconds(options.get("REPORT_STEP", ""), "输出步长"))
    routing_step = _parse_step_seconds(options.get("ROUTING_STEP", ""), "路由步长", True)
    return {
        "start_datetime": start.isoformat(),
        "end_datetime": end.isoformat(),
        "duration_seconds": duration,
        "report_step_seconds": report_step,
        "routing_step_seconds": routing_step,
        "duration_min_seconds": settings.simulation_duration_min_seconds,
        "duration_max_seconds": settings.simulation_duration_max_seconds,
        "report_step_min_seconds": settings.report_step_min_seconds,
        "max_output_steps": settings.simulation_max_output_steps,
        "require_report_step_divisible": settings.simulation_require_report_step_divisible,
    }


def apply_simulation_options(
    content: str, sections: dict[str, list[str]], values: dict[str, int], settings: Any
) -> tuple[str, list[dict]]:
    current = build_simulation_options(sections, settings)
    duration = values["duration_seconds"]
    report_step = values["report_step_seconds"]
    if isinstance(duration, bool) or not isinstance(duration, int):
        raise ParameterValidationError("模拟时长必须是整数秒")
    if isinstance(report_step, bool) or not isinstance(report_step, int):
        raise ParameterValidationError("输出步长必须是整数秒")
    if not current["duration_min_seconds"] <= duration <= current["duration_max_seconds"]:
        raise ParameterValidationError(
            f"模拟时长必须在 {current['duration_min_seconds']}～{current['duration_max_seconds']} 秒之间"
        )
    minimum_report_step = max(
        current["report_step_min_seconds"], math.ceil(current["routing_step_seconds"])
    )
    if report_step < minimum_report_step:
        raise ParameterValidationError(f"输出步长不能小于 {minimum_report_step} 秒")
    if report_step > duration:
        raise ParameterValidationError("输出步长不能大于模拟时长")
    if current["require_report_step_divisible"] and duration % report_step:
        raise ParameterValidationError("模拟时长必须能被输出步长整除")
    output_steps = duration // report_step
    if output_steps > current["max_output_steps"]:
        raise ParameterValidationError(
            f"预计输出 {output_steps} 个时间点，不能超过 {current['max_output_steps']} 个"
        )

    start = datetime.fromisoformat(current["start_datetime"])
    end = start + timedelta(seconds=duration)
    replacements = {
        "END_DATE": end.strftime("%m/%d/%Y"),
        "END_TIME": end.strftime("%H:%M:%S"),
        "REPORT_STEP": _format_step(report_step),
    }
    old_options = _option_values(sections)
    pending = dict(replacements)
    applied = []
    output = []
    current_section = ""
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].upper()
        if current_section != "OPTIONS" or not stripped or stripped.startswith(";"):
            output.append(line)
            continue
        tokens = stripped.split()
        option = tokens[0] if tokens else ""
        if option not in pending:
            output.append(line)
            continue
        new_value = pending.pop(option)
        old_value = old_options.get(option, "")
        newline = "\n" if line.endswith(("\n", "\r")) else ""
        output.append(f"{option:<21}{new_value}{newline}")
        if new_value != old_value:
            applied.append(
                {
                    "operation": "set",
                    "section": "OPTIONS",
                    "target": option,
                    "field": "value",
                    "old_value": old_value,
                    "new_value": new_value,
                    "label": OPTION_LABELS[option],
                    "unit": "",
                }
            )
    if pending:
        raise ParameterValidationError("[OPTIONS] 缺少配置项：" + ", ".join(pending))
    return "".join(output), applied


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
    "SUBCATCHMENTS.imperv": FieldSpec("SUBCATCHMENTS", "imperv", "不透水率", "%", 0, 100, 0.1),
    "SUBCATCHMENTS.slope": FieldSpec("SUBCATCHMENTS", "slope", "平均坡度", "%", 0, 100, 0.01),
    "SUBAREAS.n_imperv": FieldSpec("SUBAREAS", "n_imperv", "不透水区曼宁系数", "", 0.001, 1, 0.001),
    "SUBAREAS.n_perv": FieldSpec("SUBAREAS", "n_perv", "透水区曼宁系数", "", 0.001, 1, 0.001),
    "SUBAREAS.s_imperv": FieldSpec("SUBAREAS", "s_imperv", "不透水区洼蓄量", "mm", 0, 1000, 0.1),
    "SUBAREAS.s_perv": FieldSpec("SUBAREAS", "s_perv", "透水区洼蓄量", "mm", 0, 1000, 0.1),
    "SUBAREAS.pct_zero": FieldSpec("SUBAREAS", "pct_zero", "零洼蓄不透水区比例", "%", 0, 100, 0.1),
    "INFILTRATION.param5": FieldSpec("INFILTRATION", "param5", "下渗参数 5", "", 0, 100000, 0.1),
    "JUNCTIONS.elevation": FieldSpec(
        "JUNCTIONS", "elevation", "底部高程", "m", -10000, 10000, 0.01
    ),
    "JUNCTIONS.max_depth": FieldSpec(
        "JUNCTIONS", "max_depth", "最大深度", "m", 0.0001, 10000, 0.01
    ),
    "OUTFALLS.elevation": FieldSpec("OUTFALLS", "elevation", "排口高程", "m", -10000, 10000, 0.01),
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
