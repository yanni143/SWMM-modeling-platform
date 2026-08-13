import re
from datetime import datetime, timedelta
from typing import Any

from Tools.InpTools.InpParameterEditor import ParameterValidationError


CHICAGO_R = 0.43
IDF_N = 0.70
IDF_B_MIN = 7.0
DT_SECONDS = 60
DESIGN_RAIN_MARKER = ";@DESIGN_RAIN"

RETURN_PERIODS: dict[str, dict[str, Any]] = {
    "3year": {"label": "三年一遇", "peak_mm_h": 60.0},
    "5year": {"label": "五年一遇", "peak_mm_h": 71.4},
    "10year": {"label": "十年一遇", "peak_mm_h": 87.6},
}


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
        return dict(re.findall(r"(\w+)=([^\s]+)", stripped))
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
        rain_start, rain_end, peak_model = 0, simulation_duration, 0.0
    else:
        rain_start = nonzero[0][0]
        rain_end = min(simulation_duration, nonzero[-1][0] + DT_SECONDS)
        peak_model = max(value for _, value in nonzero)
    flow_units = _option(sections, "FLOW_UNITS").upper()
    peak_mm_h = peak_model * 25.4 if flow_units in {"CFS", "GPM", "MGD"} else peak_model
    return_period = min(
        RETURN_PERIODS,
        key=lambda item: abs(RETURN_PERIODS[item]["peak_mm_h"] - peak_mm_h),
    )
    return {
        "start_seconds": rain_start,
        "end_seconds": rain_end,
        "return_period": return_period,
    }


def build_rainfall_options(
    sections: dict[str, list[str]], simulation_duration: int
) -> dict[str, Any]:
    gage_name, series_name = _rain_gage(sections)
    metadata = _metadata(sections)
    if metadata:
        try:
            current = {
                "start_seconds": int(metadata["start_s"]),
                "end_seconds": int(metadata["end_s"]),
                "return_period": metadata["return_period"],
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
            "available_return_periods": [
                {"value": key, **value} for key, value in RETURN_PERIODS.items()
            ],
        }
    )
    return current


def _validate(values: dict[str, Any], simulation_duration: int) -> tuple[int, int, str]:
    start = values.get("start_seconds")
    end = values.get("end_seconds")
    return_period = values.get("return_period")
    if isinstance(start, bool) or not isinstance(start, int):
        raise ParameterValidationError("降雨开始时间必须是整数秒")
    if isinstance(end, bool) or not isinstance(end, int):
        raise ParameterValidationError("降雨结束时间必须是整数秒")
    if start < 0 or start >= end:
        raise ParameterValidationError("降雨时间必须满足 0 ≤ 开始时间 < 结束时间")
    if end > simulation_duration:
        raise ParameterValidationError("降雨结束时间不能超过模拟时长")
    if start % DT_SECONDS or end % DT_SECONDS:
        raise ParameterValidationError(f"降雨开始和结束时间必须是 {DT_SECONDS} 秒的整数倍")
    if return_period not in RETURN_PERIODS:
        raise ParameterValidationError("不支持的降雨重现期")
    return start, end, return_period


def _instant_mm_h(t_from_peak_min: float, *, rising: bool, amplitude: float) -> float:
    scale = CHICAGO_R if rising else 1.0 - CHICAGO_R
    t = max(0.0, t_from_peak_min)
    denominator = (t / scale + IDF_B_MIN) ** (IDF_N + 1.0)
    return amplitude * ((1.0 - IDF_N) * t / scale + IDF_B_MIN) / denominator


def build_chicago_series(
    start_seconds: int,
    end_seconds: int,
    return_period: str,
    simulation_duration: int,
) -> list[tuple[int, float]]:
    duration = end_seconds - start_seconds
    peak = RETURN_PERIODS[return_period]["peak_mm_h"]
    amplitude = peak * (IDF_B_MIN**IDF_N)
    peak_seconds = CHICAGO_R * duration
    peak_interval = int(peak_seconds // DT_SECONDS) * DT_SECONDS
    series: list[tuple[int, float]] = []
    for offset in range(0, simulation_duration + 1, DT_SECONDS):
        if offset < start_seconds or offset >= end_seconds:
            intensity = 0.0
        else:
            local_offset = offset - start_seconds
            if local_offset == peak_interval:
                intensity = peak
            else:
                midpoint = local_offset + DT_SECONDS / 2.0
                rising = midpoint <= peak_seconds
                distance_min = abs(midpoint - peak_seconds) / 60.0
                intensity = _instant_mm_h(distance_min, rising=rising, amplitude=amplitude)
        series.append((offset, max(0.0, intensity)))
    if series[-1][0] != simulation_duration:
        series.append((simulation_duration, 0.0))
    return series


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
    start, end, return_period = _validate(values, simulation_duration)
    current = build_rainfall_options(sections, simulation_duration)
    _, series_name = _rain_gage(sections)
    flow_units = _option(sections, "FLOW_UNITS").upper()
    imperial = flow_units in {"CFS", "GPM", "MGD"}
    generated = build_chicago_series(start, end, return_period, simulation_duration)

    rain_gages: list[str] = []
    for line in sections.get("RAINGAGES", []):
        tokens = line.split()
        if tokens and not line.lstrip().startswith(";"):
            upper = [token.upper() for token in tokens]
            if "TIMESERIES" in upper and upper.index("TIMESERIES") >= 4:
                tokens[2] = "0:01"
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
        f"{DESIGN_RAIN_MARKER} return_period={return_period} start_s={start} "
        f"end_s={end} dt_s={DT_SECONDS}"
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
        ("end_seconds", "降雨结束时间", "秒"),
        ("return_period", "降雨强度", ""),
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
