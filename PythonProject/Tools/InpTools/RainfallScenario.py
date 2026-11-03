"""Rainfall sources produce interval depths; every source uses the same INP editor."""

import json
import math
from functools import lru_cache
from typing import Any

from study_areas import JJ_REAL_INPUT_PATH
from Tools.InpTools.ChicagoRainfall import PEAK_RATIO, chicago_intensity_series
from Tools.InpTools.InpParameterEditor import (
    ParameterValidationError,
    apply_simulation_options,
    build_simulation_options,
)
from Tools.InpTools.InpParser import INPParser
from Tools.InpTools.InpRainfallEditor import _validate
from Tools.InpTools.RainfallSeries import (
    read_series,
    replace_series,
    series_checksum,
    validate_series,
)

EVENT_ID = "jj_real_20260913_2d"
RESOURCE = JJ_REAL_INPUT_PATH.with_suffix(".json")


@lru_cache(maxsize=1)
def _event_data() -> dict:
    return json.loads(RESOURCE.read_text(encoding="utf-8"))


def series_statistics(start: int, step: int, values: list[float]) -> dict:
    return {
        "start_seconds": start,
        "duration_seconds": step * len(values),
        "end_seconds": start + step * len(values),
        "time_step_seconds": step,
        "values_mm": values,
        "total_rainfall_mm": round(math.fsum(values), 10),
        "peak_rainfall_mm_h": max(values, default=0) * 3600 / step,
        "series_checksum": series_checksum(start, step, values),
    }


def real_event(settings: Any = None) -> dict[str, Any]:
    data = _event_data()
    stats = series_statistics(0, data["time_step_seconds"], data["values_mm"])
    return {
        **data,
        **stats,
        "simulation_duration_seconds": stats["duration_seconds"],
        "report_step_seconds": 300,
    }


def prepare_rainfall(requested: dict, study_area: str, duration: int) -> dict:
    mode = requested.get("mode", "design")
    start = requested.get("start_seconds")
    if start is None:
        start = 0
    event_id = None
    if mode == "design":
        start, wet_duration, _, total = _validate(requested, duration)
        step = 300
        values = [
            intensity * step / 3600
            for _, intensity in chicago_intensity_series(wet_duration / 3600, total)
        ]
    elif mode == "real":
        if study_area != "JJ":
            raise ParameterValidationError("老城研究区暂无内置真实降雨事件，可使用自定义序列")
        if requested.get("event_id") != EVENT_ID:
            raise ParameterValidationError("不支持的真实降雨事件")
        event = real_event()
        event_id, step, values = EVENT_ID, event["time_step_seconds"], event["values_mm"]
        if any(
            requested.get(field) is not None
            for field in ("duration_seconds", "total_rainfall_mm", "time_step_seconds", "values_mm")
        ):
            raise ParameterValidationError("真实降雨序列不可修改；如需编辑请使用自定义序列")
    elif mode == "custom":
        step, values = requested.get("time_step_seconds"), requested.get("values_mm")
    else:
        raise ParameterValidationError("不支持的降雨来源")
    values = validate_series(start, step, values, duration)
    return {**series_statistics(start, step, values), "mode": mode, "event_id": event_id}


def rainfall_catalog(
    sections: dict[str, list[str]],
    study_area: str,
    settings: Any,
    rainfall_mode: str = "design",
) -> dict[str, Any]:
    simulation = build_simulation_options(sections, settings)
    series = read_series(sections, simulation["duration_seconds"])
    mode = series["mode"] or rainfall_mode
    return {
        **series,
        **series_statistics(
            series["start_seconds"], series["time_step_seconds"], series["values_mm"]
        ),
        "mode": mode,
        "event_id": series["event_id"] or (EVENT_ID if mode == "real" else None),
        "peak_ratio": PEAK_RATIO,
        "formula": {"design": "runswmm_chicago", "real": "observed", "custom": "custom_series"}[
            mode
        ],
        "read_only": mode == "real",
        "real_event": real_event() if study_area == "JJ" else None,
    }


def apply_rainfall_scenario(
    content: str,
    study_area: str,
    settings: Any,
    simulation_options: dict[str, int] | None = None,
    rainfall_options: dict[str, Any] | None = None,
    *,
    rainfall_mode: str = "design",
) -> tuple[str, list[dict]]:
    # Read before shortening OPTIONS so existing rain cannot be silently truncated.
    current = rainfall_catalog(INPParser.parse(content), study_area, settings, rainfall_mode)
    changes = []
    if simulation_options:
        content, changes = apply_simulation_options(
            content,
            INPParser.parse(content),
            simulation_options,
            settings,
        )
    sections = INPParser.parse(content)
    duration = build_simulation_options(sections, settings)["duration_seconds"]
    if rainfall_options is not None:
        prepared = prepare_rainfall(rainfall_options, study_area, duration)
        content, rain_changes = replace_series(
            content,
            sections,
            start=prepared["start_seconds"],
            step=prepared["time_step_seconds"],
            values=prepared["values_mm"],
            duration=duration,
            mode=prepared["mode"],
            event_id=prepared["event_id"],
        )
        changes.extend(rain_changes)
    elif current["end_seconds"] > duration:
        raise ParameterValidationError("模拟时长不能短于现有降雨序列，请同时调整降雨条件")
    return content, changes
