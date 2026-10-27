"""Built-in rainfall events and version-preserving scenario transitions."""

import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from Tools.InpTools.InpParameterEditor import (
    ParameterValidationError,
    apply_simulation_options,
    build_simulation_options,
)
from Tools.InpTools.InpParser import INPParser
from Tools.InpTools.InpRainfallEditor import (
    DESIGN_BACKUP_MARKER,
    DESIGN_RAIN_MARKER,
    REAL_RAIN_MARKER,
    _option,
    _rain_gage,
    _records,
    _replace_sections,
    apply_rainfall_options,
    build_rainfall_options,
)

EVENT_ID = "jj_real_20260913_2d"
RESOURCE = Path(__file__).resolve().parents[2] / "resources/rainfall/jj/JJ_real_20260913_2d.inp"


@lru_cache(maxsize=1)
def _event_sections() -> dict[str, list[str]]:
    return INPParser.parse(RESOURCE.read_text(encoding="utf-8"))


def real_event(settings: Any) -> dict[str, Any]:
    sections = _event_sections()
    simulation = build_simulation_options(sections, settings)
    rain = build_rainfall_options(sections, simulation["duration_seconds"])
    return {
        "event_id": EVENT_ID,
        "label": "真实降雨（20260913）",
        "start_datetime": simulation["start_datetime"],
        "end_datetime": simulation["end_datetime"],
        "simulation_duration_seconds": simulation["duration_seconds"],
        "report_step_seconds": simulation["report_step_seconds"],
        "start_seconds": 0,
        "duration_seconds": simulation["duration_seconds"],
        "total_rainfall_mm": rain["total_rainfall_mm"],
        "peak_rainfall_mm_h": rain["peak_rainfall_mm_h"],
        "time_step_seconds": rain["time_step_seconds"],
    }


def _design_defaults(sections: dict[str, list[str]], settings: Any) -> dict[str, Any]:
    simulation = build_simulation_options(sections, settings)
    rain = build_rainfall_options(sections, simulation["duration_seconds"])
    if rain["mode"] == "real":
        for line in sections["TIMESERIES"]:
            if line.startswith(DESIGN_BACKUP_MARKER + " "):
                return json.loads(line[len(DESIGN_BACKUP_MARKER) + 1 :])
        raise ParameterValidationError("真实降雨版本缺少模拟降雨恢复配置")
    return {
        "start_datetime": simulation["start_datetime"],
        "duration_seconds": simulation["duration_seconds"],
        "report_step_seconds": simulation["report_step_seconds"],
        "start_seconds": rain["start_seconds"],
        "rain_duration_seconds": rain["duration_seconds"],
        "total_rainfall_mm": rain["total_rainfall_mm"],
    }


def rainfall_catalog(
    sections: dict[str, list[str]], study_area: str, settings: Any
) -> dict[str, Any]:
    simulation = build_simulation_options(sections, settings)
    rain = build_rainfall_options(sections, simulation["duration_seconds"])
    rain.update(
        available_modes=["design", "real"] if study_area == "JJ" else ["design"],
        real_event=real_event(settings) if study_area == "JJ" else None,
        design_defaults=_design_defaults(sections, settings),
    )
    return rain


def _change(section: str, target: str, field: str, old: Any, new: Any, label: str) -> dict:
    return {
        "operation": "set",
        "section": section,
        "target": target,
        "field": field,
        "old_value": str(old),
        "new_value": str(new),
        "label": label,
        "unit": "",
    }


def _set_window(content: str, start_datetime: str, duration: int) -> tuple[str, list[dict]]:
    sections = INPParser.parse(content)
    start = datetime.fromisoformat(start_datetime)
    end = start + timedelta(seconds=duration)
    replacements = {
        "START_DATE": (start.strftime("%m/%d/%Y"), "模拟开始日期"),
        "START_TIME": (start.strftime("%H:%M:%S"), "模拟开始时间"),
        "REPORT_START_DATE": (start.strftime("%m/%d/%Y"), "输出开始日期"),
        "REPORT_START_TIME": (start.strftime("%H:%M:%S"), "输出开始时间"),
        "END_DATE": (end.strftime("%m/%d/%Y"), "模拟结束日期"),
        "END_TIME": (end.strftime("%H:%M:%S"), "模拟结束时间"),
    }
    changes = []
    lines = []
    for line in sections["OPTIONS"]:
        tokens = line.split()
        if tokens and tokens[0] in replacements:
            value, label = replacements[tokens[0]]
            if tokens[1] != value:
                changes.append(_change("OPTIONS", tokens[0], "value", tokens[1], value, label))
            line = f"{tokens[0]:<21}{value}"
        lines.append(line)
    return _replace_sections(content, {"OPTIONS": lines}), changes


def _inject_real(content: str, backup: dict[str, Any]) -> str:
    sections = INPParser.parse(content)
    _, series_name = _rain_gage(sections)
    source = _event_sections()
    _, source_name = _rain_gage(source)
    imperial = _option(sections, "FLOW_UNITS").upper() in {"CFS", "GPM", "MGD"}
    series = [
        line
        for line in sections["TIMESERIES"]
        if not line.startswith((DESIGN_RAIN_MARKER, REAL_RAIN_MARKER, DESIGN_BACKUP_MARKER))
        and (line.startswith(";") or line.split()[0].lower() != series_name.lower())
    ]
    series.extend(
        [
            f"{REAL_RAIN_MARKER} {EVENT_ID}",
            f"{DESIGN_BACKUP_MARKER} {json.dumps(backup, separators=(',', ':'))}",
        ]
    )
    for tokens in _records(source["TIMESERIES"]):
        if tokens[0] == source_name:
            value = float(tokens[3]) / 25.4 if imperial else float(tokens[3])
            series.append(f"{series_name} {tokens[1]} {tokens[2]} {value:.12g}")
    gages = []
    for line in sections["RAINGAGES"]:
        tokens = line.split()
        if (
            len(tokens) >= 6
            and not line.startswith(";")
            and tokens[4].upper() == "TIMESERIES"
            and tokens[5].lower() == series_name.lower()
        ):
            tokens[1:4] = ["CUMULATIVE", "00:05", "1.0"]
            line = " ".join(tokens)
        gages.append(line)
    return _replace_sections(content, {"RAINGAGES": gages, "TIMESERIES": series})


def apply_rainfall_scenario(
    content: str,
    study_area: str,
    settings: Any,
    simulation_options: dict[str, int] | None = None,
    rainfall_options: dict[str, Any] | None = None,
) -> tuple[str, list[dict]]:
    """Validate transitions before touching a saved version or regenerating rain."""
    sections = INPParser.parse(content)
    simulation = build_simulation_options(sections, settings)
    current = build_rainfall_options(sections, simulation["duration_seconds"])
    requested = rainfall_options or {}
    mode = requested.get("mode", current["mode"])
    if mode not in {"design", "real"}:
        raise ParameterValidationError("不支持的降雨类型")
    if mode == "real" and study_area != "JJ":
        raise ParameterValidationError("老城研究区仅支持模拟降雨")
    changes = []
    if mode == "real":
        event = real_event(settings)
        event_id = requested.get("event_id") or current["event_id"] or EVENT_ID
        if event_id != EVENT_ID:
            raise ParameterValidationError("不支持的真实降雨事件")
        for field in ("start_seconds", "duration_seconds", "total_rainfall_mm"):
            if requested.get(field) is not None and requested[field] != event[field]:
                raise ParameterValidationError("真实降雨的开始时间、时长和总雨量不可修改")
        if (
            simulation_options
            and simulation_options["duration_seconds"] != event["simulation_duration_seconds"]
        ):
            raise ParameterValidationError("真实降雨的模拟时长固定为 172800 秒（48 小时）")
        # Preserve the exact observed series for engineering-only descendants.
        if current["mode"] == "real" and not simulation_options:
            return content, []
        if current["mode"] != "real":
            backup = _design_defaults(sections, settings)
            content = _inject_real(content, backup)
            content, start_changes = _set_window(
                content, event["start_datetime"], event["simulation_duration_seconds"]
            )
            changes.extend(start_changes)
        report_step = simulation["report_step_seconds"]
        if not simulation_options and (
            event["simulation_duration_seconds"] // report_step
            > settings.simulation_max_output_steps
            or (
                settings.simulation_require_report_step_divisible
                and event["simulation_duration_seconds"] % report_step
            )
        ):
            report_step = event["report_step_seconds"]
        target = simulation_options or {
            "duration_seconds": event["simulation_duration_seconds"],
            "report_step_seconds": report_step,
        }
        content, option_changes = apply_simulation_options(
            content, INPParser.parse(content), target, settings
        )
        changes.extend(option_changes)
    else:
        switching = current["mode"] == "real"
        if switching:
            backup = _design_defaults(sections, settings)
            content, start_changes = _set_window(
                content, backup["start_datetime"], backup["duration_seconds"]
            )
            changes.extend(start_changes)
            simulation_options = simulation_options or {
                "duration_seconds": backup["duration_seconds"],
                "report_step_seconds": backup["report_step_seconds"],
            }
        if simulation_options:
            content, option_changes = apply_simulation_options(
                content, INPParser.parse(content), simulation_options, settings
            )
            changes.extend(option_changes)
        effective = build_simulation_options(INPParser.parse(content), settings)
        values = {
            "start_seconds": requested.get("start_seconds"),
            "duration_seconds": requested.get("duration_seconds"),
            "total_rainfall_mm": requested.get("total_rainfall_mm"),
        }
        fallback = {
            "start_seconds": backup["start_seconds"] if switching else current["start_seconds"],
            "duration_seconds": backup["rain_duration_seconds"]
            if switching
            else current["duration_seconds"],
            "total_rainfall_mm": backup["total_rainfall_mm"]
            if switching
            else current["total_rainfall_mm"],
        }
        values = {
            key: value if value is not None else fallback[key] for key, value in values.items()
        }
        if switching or rainfall_options or current["end_seconds"] > effective["duration_seconds"]:
            content, rain_changes = apply_rainfall_options(
                content, INPParser.parse(content), values, effective["duration_seconds"]
            )
            changes.extend(rain_changes)
    if mode != current["mode"]:
        changes.append(
            _change(
                "RAINGAGES",
                current["gage_name"],
                "rainfall_mode",
                current["mode"],
                mode,
                "降雨类型",
            )
        )
        changes.append(
            _change(
                "TIMESERIES",
                current["series_name"],
                "event_id",
                current["event_id"] or "",
                EVENT_ID if mode == "real" else "",
                "真实降雨事件",
            )
        )
    return content, changes
