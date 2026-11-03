"""Rainfall interchange: each value is mm over [start + i*step, start + (i+1)*step)."""

import hashlib
import json
import math
import re
from datetime import timedelta
from typing import Any

from Tools.InpTools.InpParameterEditor import ParameterValidationError
from Tools.InpTools.InpRainfallEditor import (
    _option,
    _parse_series_time,
    _rain_gage,
    _records,
    _replace_sections,
    _simulation_start,
    build_rainfall_options,
)

MARKER = ";@RAINFALL"
MAX_VALUES = 10000


def validate_series(start: int, step: int, values: list[float], duration: int) -> list[float]:
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise ParameterValidationError("降雨开始时间必须是不小于 0 的整数秒")
    if isinstance(step, bool) or not isinstance(step, int) or step <= 0:
        raise ParameterValidationError("降雨记录间隔必须是大于 0 的整数秒")
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_VALUES:
        raise ParameterValidationError(f"降雨序列须包含 1～{MAX_VALUES} 条记录")
    normalized = []
    for index, value in enumerate(values, 1):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ParameterValidationError(f"降雨序列第 {index} 行必须是不小于 0 的有限雨量（mm）")
        normalized.append(float(f"{value:.12g}"))
    if start + step * len(values) > duration:
        raise ParameterValidationError(
            f"降雨序列覆盖到 {start + step * len(values)} 秒，超过模拟时长 {duration} 秒；"
            "请调整模拟时长或降雨序列"
        )
    return normalized


def series_checksum(start: int, step: int, values: list[float]) -> str:
    payload = [start, step, [f"{value:.12g}" for value in values]]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def read_series(sections: dict[str, list[str]], duration: int) -> dict[str, Any]:
    """Read both legacy INPs and the normalized VOLUME sequences written below."""
    gage_name, name = _rain_gage(sections)
    gage = next(row for row in _records(sections["RAINGAGES"]) if row[0] == gage_name)
    interval = gage[2].split(":")
    step = (
        sum(int(part) * factor for part, factor in zip(interval, (3600, 60, 1)))
        if len(interval) in {2, 3}
        else round(float(gage[2]) * 3600)
    )
    if step <= 0:
        raise ParameterValidationError("雨量计记录间隔必须大于 0")
    model_start = _simulation_start(sections)
    conversion = 25.4 if _option(sections, "FLOW_UNITS").upper() in {"CFS", "GPM", "MGD"} else 1
    by_time: dict[int, float] = {}
    previous = 0.0
    last_date = ""
    for row in _records(sections.get("TIMESERIES", [])):
        if row[0].lower() != name.lower():
            continue
        if len(row) >= 4:
            last_date = row[1]
            stamp = _parse_series_time(last_date, row[2], model_start)
            raw = float(row[3])
        elif len(row) == 3:
            stamp = _parse_series_time(last_date, row[1], model_start)
            raw = float(row[2])
        else:
            raise ParameterValidationError("降雨时间序列记录格式无效")
        offset = int((stamp - model_start).total_seconds())
        if not math.isfinite(raw) or raw < 0 or offset in by_time:
            raise ParameterValidationError("降雨时间序列包含无效雨量或重复时间")
        if gage[1].upper() == "CUMULATIVE":
            value = raw - previous if raw >= previous else raw
            previous = raw
        elif gage[1].upper() == "VOLUME":
            value = raw
        elif gage[1].upper() == "INTENSITY":
            value = raw * step / 3600
        else:
            raise ParameterValidationError("不支持的雨量计数据格式")
        by_time[offset] = value * conversion
    metadata = None
    for line in sections.get("TIMESERIES", []):
        if line.strip().startswith(MARKER + " "):
            metadata = dict(re.findall(r"(\w+)=([^\s]+)", line))
    if metadata:
        start = int(metadata["start_s"])
        count = int(metadata["count"])
    else:
        # Legacy design metadata describes the wet interval. Observed inputs cover
        # the complete simulation, including dry periods and their end sentinel.
        options = build_rainfall_options(sections, duration)
        start = options["start_seconds"]
        count = math.ceil(options["duration_seconds"] / step)
        if gage[1].upper() == "CUMULATIVE":
            start, count = 0, math.ceil(duration / step)
    if not 1 <= count <= MAX_VALUES:
        raise ParameterValidationError("降雨序列记录数量超出支持范围")
    values = [float(f"{by_time.get(start + index * step, 0):.12g}") for index in range(count)]
    return {
        "start_seconds": start,
        "time_step_seconds": step,
        "values_mm": values,
        "series_checksum": series_checksum(start, step, values),
        "mode": metadata.get("mode", "design") if metadata else None,
        "event_id": metadata.get("event_id") if metadata else None,
        "gage_name": gage_name,
        "series_name": name,
    }


def replace_series(
    content: str,
    sections: dict[str, list[str]],
    *,
    start: int,
    step: int,
    values: list[float],
    duration: int,
    mode: str,
    event_id: str | None = None,
) -> tuple[str, list[dict]]:
    values = validate_series(start, step, values, duration)
    current = read_series(sections, duration)
    checksum = series_checksum(start, step, values)
    if (
        current["series_checksum"] == checksum
        and current["mode"] == mode
        and current["event_id"] == event_id
    ):
        return content, []
    name = current["series_name"]
    gages = []
    for line in sections["RAINGAGES"]:
        tokens = line.split()
        if (
            tokens
            and not line.lstrip().startswith(";")
            and len(tokens) >= 6
            and tokens[4].upper() == "TIMESERIES"
            and tokens[5].lower() == name.lower()
        ):
            tokens[1:3] = ["VOLUME", f"{step // 3600}:{step % 3600 // 60:02d}:{step % 60:02d}"]
            line = " ".join(tokens)
        gages.append(line)
    lines = []
    for line in sections.get("TIMESERIES", []):
        stripped = line.strip()
        if any(
            stripped.startswith(marker)
            for marker in (
                MARKER,
                ";@DESIGN_RAIN",
                ";@REAL_RAIN",
                ";@DESIGN_BACKUP",
            )
        ):
            continue
        if (
            stripped
            and not stripped.startswith(";")
            and stripped.split()[0].lower() == name.lower()
        ):
            continue
        lines.append(line)
    lines.append(
        f"{MARKER} schema=1 mode={mode} start_s={start} dt_s={step} count={len(values)}"
        + (f" event_id={event_id}" if event_id else "")
    )
    model_start = _simulation_start(sections)
    conversion = 25.4 if _option(sections, "FLOW_UNITS").upper() in {"CFS", "GPM", "MGD"} else 1
    rows = [(start + index * step, value) for index, value in enumerate(values)]
    # SWMM rejects consecutive rain records closer than the gage interval. A
    # first record later than model start already implies a dry leading period.
    if start >= step:
        rows.insert(0, (0, 0.0))
    rows.append((start + len(values) * step, 0.0))
    for offset, value in rows:
        stamp = model_start + timedelta(seconds=offset)
        lines.append(f"{name:<20} {stamp:%m/%d/%Y} {stamp:%H:%M:%S} {value / conversion:.15g}")
    adjusted = _replace_sections(content, {"RAINGAGES": gages, "TIMESERIES": lines})
    return adjusted, [
        {
            "operation": "set",
            "section": "TIMESERIES",
            "target": name,
            "field": "rainfall_series",
            "old_value": current["series_checksum"],
            "new_value": checksum,
            "label": "降雨序列",
            "unit": "",
        }
    ]
