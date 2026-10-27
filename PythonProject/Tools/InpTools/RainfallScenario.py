"""Describe input scenarios and edit parameters within the selected input."""

from functools import lru_cache
from typing import Any

from study_areas import JJ_REAL_INPUT_PATH
from Tools.InpTools.InpParameterEditor import (
    ParameterValidationError,
    apply_simulation_options,
    build_simulation_options,
)
from Tools.InpTools.InpParser import INPParser
from Tools.InpTools.InpRainfallEditor import apply_rainfall_options, build_rainfall_options

EVENT_ID = "jj_real_20260913_2d"
RESOURCE = JJ_REAL_INPUT_PATH


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


def rainfall_catalog(
    sections: dict[str, list[str]], study_area: str, settings: Any, rainfall_mode: str = "design"
) -> dict[str, Any]:
    simulation = build_simulation_options(sections, settings)
    rain = build_rainfall_options(sections, simulation["duration_seconds"])
    event = real_event(settings) if study_area == "JJ" else None
    if rainfall_mode == "real":
        if not event:
            raise ParameterValidationError("老城研究区仅支持模拟降雨")
        rain.update(
            mode="real",
            event_id=EVENT_ID,
            read_only=True,
            start_seconds=event["start_seconds"],
            duration_seconds=event["duration_seconds"],
            end_seconds=event["duration_seconds"],
            formula="observed_cumulative",
        )
    rain["real_event"] = event
    return rain


def apply_rainfall_scenario(
    content: str,
    study_area: str,
    settings: Any,
    simulation_options: dict[str, int] | None = None,
    rainfall_options: dict[str, Any] | None = None,
    *,
    rainfall_mode: str = "design",
) -> tuple[str, list[dict]]:
    """Changing inputs is selection, never a parameter-save operation."""
    requested = rainfall_options or {}
    if requested.get("mode", rainfall_mode) != rainfall_mode:
        raise ParameterValidationError("请通过输入方案选择切换降雨类型，无需保存参数")
    sections = INPParser.parse(content)
    current = rainfall_catalog(sections, study_area, settings, rainfall_mode)
    if rainfall_mode == "real":
        event = real_event(settings)
        if requested.get("event_id") not in {None, EVENT_ID}:
            raise ParameterValidationError("不支持的真实降雨事件")
        for field in ("start_seconds", "duration_seconds", "total_rainfall_mm"):
            if requested.get(field) is not None and requested[field] != event[field]:
                raise ParameterValidationError("真实降雨的开始时间、时长和总雨量不可修改")
        if (
            simulation_options
            and simulation_options["duration_seconds"] != event["simulation_duration_seconds"]
        ):
            raise ParameterValidationError("真实降雨的模拟时长固定为 172800 秒（48 小时）")
        if simulation_options:
            return apply_simulation_options(content, sections, simulation_options, settings)
        return content, []
    changes = []
    if simulation_options:
        content, changes = apply_simulation_options(content, sections, simulation_options, settings)
    effective = build_simulation_options(INPParser.parse(content), settings)
    if rainfall_options or current["end_seconds"] > effective["duration_seconds"]:
        values = {
            field: requested.get(field, current[field])
            for field in ("start_seconds", "duration_seconds", "total_rainfall_mm")
        }
        content, rain_changes = apply_rainfall_options(
            content, INPParser.parse(content), values, effective["duration_seconds"]
        )
        changes.extend(rain_changes)
    return content, changes
