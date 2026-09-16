import re
from datetime import datetime, timedelta
from typing import Any

from Tools.InpTools.InpParameterEditor import ParameterValidationError
from Tools.InpTools.ChicagoRainfall import PEAK_RATIO, STEP_MINUTES, chicago_intensity_series


CHICAGO_R = PEAK_RATIO
DT_SECONDS = STEP_MINUTES * 60
DESIGN_RAIN_MARKER = ";@DESIGN_RAIN"
DESIGN_RAIN_FORMULA = "runswmm_chicago"


def _records(lines: list[str]) -> list[list[str]]:
    return [line.split() for line in lines if line.strip() and not line.lstrip().startswith(";")]


def _option(sections: dict[str, list[str]], name: str) -> str:
    for tokens in _records(sections.get("OPTIONS", [])):
        if tokens[0].upper() == name:
            return tokens[1] if len(tokens) > 1 else ""
    return ""


def _simulation_start(sections: dict[str, list[str]]) -> datetime:
    try:
        return datetime.strptime(  # noqa: DTZ007
            f"{_option(sections, 'START_DATE')} {_option(sections, 'START_TIME')}",
            "%m/%d/%Y %H:%M:%S",
        )
    except ValueError as exc:
        raise ParameterValidationError("无法读取模拟开始日期时间") from exc


def _rain_gage(sections: dict[str, list[str]]) -> tuple[str, str]:
    referenced: list[tuple[str, str]] = []
    for tokens in _records(sections.get("RAINGAGES", [])):
        upper = [token.upper() for token in tokens]
        if "TIMESERIES" not in upper:
            continue
        position = upper.index("TIMESERIES")
        if position + 1 < len(tokens):
            referenced.append((tokens[0], tokens[position + 1]))
    if not referenced:
        raise ParameterValidationError("[RAINGAGES] 中没有引用内嵌时间序列的雨量计")
    series_names = {series.lower() for _, series in referenced}
    if len(series_names) != 1:
        raise ParameterValidationError("第一版设计降雨仅支持所有雨量计引用同一时间序列")
    return referenced[0]


def _metadata(sections: dict[str, list[str]]) -> dict[str, str] | None:
    for line in sections.get("TIMESERIES", []):
        stripped = line.strip()
        if not stripped.startswith(DESIGN_RAIN_MARKER):
            continue
        metadata = dict(re.findall(r"(\w+)=([^\s]+)", stripped))
        if metadata.get("schema") == "2":
            return metadata
    return None


def _parse_series_time(date_text: str, time_text: str, start: datetime) -> datetime:
    if date_text:
        formats = ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M")
        for fmt in formats:
            try:
                return datetime.strptime(f"{date_text} {time_text}", fmt)  # noqa: DTZ007
            except ValueError:
                pass
    parts = time_text.split(":")
    if len(parts) == 2:
        return start + timedelta(hours=int(parts[0]), minutes=int(parts[1]))
    if len(parts) == 3:
        return start + timedelta(hours=int(parts[0]), minutes=int(parts[1]), seconds=int(parts[2]))
    return start + timedelta(hours=float(time_text))


def _infer_existing_options(
    sections: dict[str, list[str]], series_name: str, simulation_duration: int
) -> dict[str, Any]:
    start = _simulation_start(sections)
    values: list[tuple[int, float]] = []
    for tokens in _records(sections.get("TIMESERIES", [])):
        if not tokens or tokens[0].lower() != series_name.lower():
            continue
        try:
            if len(tokens) >= 4:
                stamp = _parse_series_time(tokens[1], tokens[2], start)
                value = float(tokens[3])
            elif len(tokens) >= 3:
                stamp = _parse_series_time("", tokens[1], start)
                value = float(tokens[2])
            else:
                continue
        except (ValueError, OverflowError):
            continue
        values.append((max(0, int((stamp - start).total_seconds())), value))
    nonzero = [(offset, value) for offset, value in values if value > 0]
    if not nonzero:
        rain_start, rain_end, peak_model, total_mm = 0, simulation_duration, 0.0, 0.0
    else:
        rain_start = nonzero[0][0]
        rain_end = min(simulation_duration, nonzero[-1][0] + DT_SECONDS)
        peak_model = max(value for _, value in nonzero)
    flow_units = _option(sections, "FLOW_UNITS").upper()
    imperial = flow_units in {"CFS", "GPM", "MGD"}
    conversion = 25.4 if imperial else 1.0
    if nonzero:
        total_mm = sum(value * conversion for _, value in nonzero) * DT_SECONDS / 3600.0
    peak_mm_h = peak_model * conversion
    return {
        "start_seconds": rain_start,
        "duration_seconds": rain_end - rain_start,
        "end_seconds": rain_end,
        "total_rainfall_mm": total_mm,
        "peak_rainfall_mm_h": peak_mm_h,
        "peak_ratio": CHICAGO_R,
        "formula": "existing_timeseries",
    }


def build_rainfall_options(
    sections: dict[str, list[str]], simulation_duration: int
) -> dict[str, Any]:
    gage_name, series_name = _rain_gage(sections)
    metadata = _metadata(sections)
    if metadata:
        try:
            start_seconds = int(metadata["start_s"])
            duration_seconds = int(metadata["duration_s"])
            current = {
                "start_seconds": start_seconds,
                "duration_seconds": duration_seconds,
                "end_seconds": start_seconds + duration_seconds,
                "total_rainfall_mm": float(metadata["total_mm"]),
                "peak_rainfall_mm_h": float(metadata.get("peak_mm_h", "0")),
                "peak_ratio": float(metadata.get("r", str(CHICAGO_R))),
                "formula": metadata.get("formula", DESIGN_RAIN_FORMULA),
            }
        except (KeyError, ValueError) as exc:
            raise ParameterValidationError("设计降雨元数据格式无效") from exc
    else:
        current = _infer_existing_options(sections, series_name, simulation_duration)
    current.update(
        {
            "gage_name": gage_name,
            "series_name": series_name,
            "time_step_seconds": DT_SECONDS,
        }
    )
    return current


def _validate(values: dict[str, Any], simulation_duration: int) -> tuple[int, int, int, float]:
    start = values.get("start_seconds")
    duration = values.get("duration_seconds")
    total_rainfall = values.get("total_rainfall_mm")
    if isinstance(start, bool) or not isinstance(start, int):
        raise ParameterValidationError("降雨开始时间必须是整数秒")
    if isinstance(duration, bool) or not isinstance(duration, int):
        raise ParameterValidationError("降雨时长必须是整数秒")
    if isinstance(total_rainfall, bool) or not isinstance(total_rainfall, (int, float)):
        raise ParameterValidationError("总降雨量必须是数值")
    total_rainfall = float(total_rainfall)
    if start < 0 or duration <= 0:
        raise ParameterValidationError("降雨开始时间必须不小于 0，降雨时长必须大于 0")
    end = start + duration
    if end > simulation_duration:
        raise ParameterValidationError("降雨结束时间不能超过模拟时长")
    if start % DT_SECONDS or duration % DT_SECONDS:
        raise ParameterValidationError(f"降雨开始时间和时长必须是 {DT_SECONDS} 秒的整数倍")
    if total_rainfall <= 0 or total_rainfall == float("inf") or total_rainfall != total_rainfall:
        raise ParameterValidationError("总降雨量必须是大于 0 的有限数值")
    return start, duration, end, total_rainfall


def build_chicago_series(
    start_seconds: int,
    duration_seconds: int,
    total_rainfall_mm: float,
    simulation_duration: int,
) -> list[tuple[int, float]]:
    try:
        wet = chicago_intensity_series(duration_seconds / 3600.0, total_rainfall_mm)
    except ValueError as exc:
        raise ParameterValidationError(str(exc)) from exc
    by_offset = {start_seconds + offset: intensity for offset, intensity in wet}
    rows = [
        (offset, by_offset.get(offset, 0.0))
        for offset in range(0, simulation_duration + 1, DT_SECONDS)
    ]
    end_seconds = start_seconds + duration_seconds
    if rows[-1][0] != simulation_duration:
        rows.append((simulation_duration, 0.0))
    if end_seconds not in dict(rows):
        rows.append((end_seconds, 0.0))
    return sorted(rows)


def _replace_sections(content: str, replacements: dict[str, list[str]]) -> str:
    output: list[str] = []
    current = ""
    replaced: set[str] = set()
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1].upper()
            output.append(line)
            if current in replacements:
                newline = "\r\n" if line.endswith("\r\n") else "\n"
                output.extend(item + newline for item in replacements[current])
                replaced.add(current)
            continue
        if current in replacements:
            continue
        output.append(line)
    missing = set(replacements) - replaced
    if missing:
        raise ParameterValidationError("INP 缺少节：" + ", ".join(sorted(missing)))
    return "".join(output)


def apply_rainfall_options(
    content: str,
    sections: dict[str, list[str]],
    values: dict[str, Any],
    simulation_duration: int,
) -> tuple[str, list[dict[str, str]]]:
    start, duration, end, total_rainfall = _validate(values, simulation_duration)
    current = build_rainfall_options(sections, simulation_duration)
    _, series_name = _rain_gage(sections)
    flow_units = _option(sections, "FLOW_UNITS").upper()
    imperial = flow_units in {"CFS", "GPM", "MGD"}
    generated = build_chicago_series(start, duration, total_rainfall, simulation_duration)
    peak_rainfall_mm_h = max(
        intensity
        for offset, intensity in generated
        if start <= offset < end
    )

    rain_gages: list[str] = []
    for line in sections.get("RAINGAGES", []):
        tokens = line.split()
        if tokens and not line.lstrip().startswith(";"):
            upper = [token.upper() for token in tokens]
            if "TIMESERIES" in upper and upper.index("TIMESERIES") >= 4:
                tokens[2] = "0:05"
                line = " ".join(tokens)
        rain_gages.append(line)

    time_series = [
        line
        for line in sections.get("TIMESERIES", [])
        if not (
            line.strip().startswith(DESIGN_RAIN_MARKER)
            or (
                line.split()
                and not line.lstrip().startswith(";")
                and line.split()[0].lower() == series_name.lower()
            )
        )
    ]
    time_series.append(
        f"{DESIGN_RAIN_MARKER} schema=2 formula={DESIGN_RAIN_FORMULA} "
        f"start_s={start} duration_s={duration} total_mm={total_rainfall:.12g} "
        f"peak_mm_h={peak_rainfall_mm_h:.12g} r={CHICAGO_R} dt_s={DT_SECONDS}"
    )
    model_start = _simulation_start(sections)
    for offset, intensity_mm_h in generated:
        stamp = model_start + timedelta(seconds=offset)
        model_value = intensity_mm_h / 25.4 if imperial else intensity_mm_h
        time_series.append(f"{series_name:<20} {stamp:%m/%d/%Y} {stamp:%H:%M:%S} {model_value:.8g}")

    adjusted = _replace_sections(content, {"RAINGAGES": rain_gages, "TIMESERIES": time_series})
    changes: list[dict[str, str]] = []
    fields = (
        ("start_seconds", "降雨开始时间", "秒"),
        ("duration_seconds", "降雨时长", "秒"),
        ("total_rainfall_mm", "总降雨量", "mm"),
    )
    for field, label, unit in fields:
        old_value = str(current[field])
        new_value = str(values[field])
        if old_value != new_value:
            changes.append(
                {
                    "operation": "set",
                    "section": "TIMESERIES",
                    "target": series_name,
                    "field": field,
                    "old_value": old_value,
                    "new_value": new_value,
                    "label": label,
                    "unit": unit,
                }
            )
    return adjusted, changes
