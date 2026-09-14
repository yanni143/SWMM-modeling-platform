from __future__ import annotations

"""只解析 SWMM 生成的 .out 二进制报告，无额外处理。

利用 pyswmm 库读取 SWMM .out 文件中的节点流量时间序列，并将其导出为 CSV 文件。支持可选的节点筛选、时间范围限制和时间重采样。
example usage:
python export_node_timeseries.py --out-file path/to/simulation.out --output path/to/output.csv `
--nodes Node1,Node2 --start "2020-01-01 00:00:00" --end "2020-01-02 00:00:00" --resample 1H
"""

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from pyswmm import Output
from swmm.toolkit.shared_enum import NodeAttribute


@dataclass(frozen=True)
class NodeSeriesRecord:
	"""Represents one exported node time-series row."""

	time: datetime
	node_id: str
	flow_m3s: float
	flooding_m3s: float | None = None
	depth_m: float | None = None
	head_m: float | None = None
	flow_mean_m3s: float | None = None
	volume_m3: float | None = None


@dataclass(frozen=True)
class ExportConfig:
	"""Configuration for the export job."""

	out_file: Path
	nodes: tuple[str, ...] | None
	start: datetime | None
	end: datetime | None
	resample: str | None
	output: Path


class ExportError(Exception):
	"""Raised when the requested export cannot be completed."""


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Export SWMM node flow time series from a .out file")
	parser.add_argument("--out-file", required=True, help="Path to the SWMM .out file")
	parser.add_argument("--nodes", help="Comma-separated node IDs to export; defaults to all nodes")
	parser.add_argument("--start", help="Optional start datetime, e.g. 2020-01-01 00:00:00")
	parser.add_argument("--end", help="Optional end datetime, e.g. 2020-01-01 12:00:00")
	parser.add_argument("--resample", help="Optional resampling frequency such as 1H or 1D")
	parser.add_argument("--output", required=True, help="Output CSV path")
	return parser.parse_args()


def parse_datetime(value: str | None) -> datetime | None:
	if value is None:
		return None
	return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_config(config: ExportConfig) -> None:
	if not config.out_file.exists():
		raise ExportError(f"SWMM output file does not exist: {config.out_file}")
	if not config.out_file.is_file():
		raise ExportError(f"SWMM output path is not a file: {config.out_file}")
	if config.output.exists() and config.output.is_dir():
		raise ExportError(f"Output path is a directory: {config.output}")
	config.output.parent.mkdir(parents=True, exist_ok=True)


def normalize_nodes(node_names: Iterable[str] | None) -> tuple[str, ...] | None:
	if node_names is None:
		return None
	return tuple(name.strip() for name in node_names if name.strip())


def _read_optional_series(out: Output, node_id: str, attribute: NodeAttribute, start_time: datetime | None, end_time: datetime | None) -> dict[datetime, float]:
	try:
		return out.node_series(node_id, attribute, start_time, end_time)
	except Exception:
		return {}


def collect_node_series(config: ExportConfig) -> list[NodeSeriesRecord]:
	"""Read node time series from the SWMM .out file.

	Assumption: node flow is read from SWMM's TOTAL_INFLOW series. This is the
	common interpretation for node discharge and is suitable for coupling
	workflows that need a volumetric flow time series.
	"""

	with Output(str(config.out_file)) as out:
		node_ids = list(out.nodes)
		if config.nodes is not None:
			missing = [node_id for node_id in config.nodes if node_id not in node_ids]
			if missing:
				raise ExportError(f"Node(s) not found in output file: {', '.join(missing)}")
			selected_nodes = config.nodes
		else:
			selected_nodes = tuple(node_ids)

		records: list[NodeSeriesRecord] = []
		for node_id in selected_nodes:
			flow_series = out.node_series(node_id, NodeAttribute.TOTAL_INFLOW, config.start, config.end)
			flood_series = _read_optional_series(out, node_id, NodeAttribute.FLOODING_LOSSES, config.start, config.end)
			depth_series = _read_optional_series(out, node_id, NodeAttribute.INVERT_DEPTH, config.start, config.end)
			head_series = _read_optional_series(out, node_id, NodeAttribute.HYDRAULIC_HEAD, config.start, config.end)
			if not flow_series:
				continue
			for timestamp, value in flow_series.items():
				flood_value = float(flood_series.get(timestamp)) if timestamp in flood_series and flood_series.get(timestamp) is not None else None
				depth_value = float(depth_series.get(timestamp)) if timestamp in depth_series and depth_series.get(timestamp) is not None else None
				head_value = float(head_series.get(timestamp)) if timestamp in head_series and head_series.get(timestamp) is not None else None
				records.append(
					NodeSeriesRecord(
						time=timestamp,
						node_id=node_id,
						flow_m3s=float(value),
						flooding_m3s=flood_value,
						depth_m=depth_value,
						head_m=head_value,
					)
				)

	if not records:
		raise ExportError("No data available for the requested time range")

	records.sort(key=lambda item: (item.time, item.node_id))
	return records


def resample_records(records: list[NodeSeriesRecord], freq: str) -> list[NodeSeriesRecord]:
	"""Resample by simple time-bin averaging.

	This implementation is intentionally lightweight and suitable for CSV export.
	It averages flow within each requested frequency window and computes a volume
	estimate from the raw interval length in seconds.
	"""
	if not records:
		return []

	freq_delta = _parse_frequency(freq)
	if freq_delta is None:
		raise ExportError(f"Unsupported resample frequency: {freq}")

	epoch = datetime(1970, 1, 1)
	buckets: dict[tuple[datetime, str], list[NodeSeriesRecord]] = {}
	for record in records:
		offset = (record.time - epoch) % freq_delta
		bucket_time = record.time - offset
		bucket_key = (bucket_time, record.node_id)
		buckets.setdefault(bucket_key, []).append(record)

	resampled: list[NodeSeriesRecord] = []
	for (bucket_time, node_id), bucket_records in sorted(buckets.items()):
		bucket_records.sort(key=lambda item: item.time)
		mean_flow = sum(item.flow_m3s for item in bucket_records) / len(bucket_records)
		if len(bucket_records) > 1:
			span_seconds = max(1, int((bucket_records[-1].time - bucket_records[0].time).total_seconds()))
		else:
			span_seconds = max(1, int(freq_delta.total_seconds()))
		volume_m3 = mean_flow * span_seconds
		resampled.append(
			NodeSeriesRecord(
				time=bucket_time,
				node_id=node_id,
				flow_m3s=mean_flow,
				flow_mean_m3s=mean_flow,
				volume_m3=volume_m3,
			)
		)
	return resampled


def _parse_frequency(freq: str) -> timedelta | None:
	freq = freq.strip().upper()
	if freq.endswith("H"):
		return timedelta(hours=int(freq[:-1]))
	if freq.endswith("D"):
		return timedelta(days=int(freq[:-1]))
	if freq.endswith("T"):
		return timedelta(minutes=int(freq[:-1]))
	if freq.endswith("S"):
		return timedelta(seconds=int(freq[:-1]))
	return None


def write_csv(records: list[NodeSeriesRecord], output_path: Path, resample: bool) -> None:
	"""Write the exported records to CSV using UTF-8 encoding."""
	output_path.parent.mkdir(parents=True, exist_ok=True)
	fieldnames = ["time", "node_id", "flow_m3s"]
	if resample:
		fieldnames.extend(["flow_mean_m3s", "volume_m3"])
	if any(record.flooding_m3s is not None for record in records):
		fieldnames.append("flooding_m3s")
	if any(record.depth_m is not None for record in records):
		fieldnames.append("depth_m")
	if any(record.head_m is not None for record in records):
		fieldnames.append("head_m")
	with output_path.open("w", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=fieldnames)
		writer.writeheader()
		for record in records:
			row = {
				"time": record.time.isoformat(),
				"node_id": record.node_id,
				"flow_m3s": format(record.flow_m3s, ".12g"),
			}
			if resample:
				row["flow_mean_m3s"] = format(record.flow_mean_m3s, ".12g") if record.flow_mean_m3s is not None else ""
				row["volume_m3"] = format(record.volume_m3, ".12g") if record.volume_m3 is not None else ""
			if record.flooding_m3s is not None:
				row["flooding_m3s"] = format(record.flooding_m3s, ".12g")
			if record.depth_m is not None:
				row["depth_m"] = format(record.depth_m, ".12g")
			if record.head_m is not None:
				row["head_m"] = format(record.head_m, ".12g")
			writer.writerow(row)


def export_node_timeseries(config: ExportConfig) -> Path:
	"""Top-level entrypoint for exporting node time series."""
	validate_config(config)
	records = collect_node_series(config)
	if config.resample:
		records = resample_records(records, config.resample)
	write_csv(records, config.output, resample=bool(config.resample))
	return config.output


def main() -> int:
	args = parse_args()
	config = ExportConfig(
		out_file=Path(args.out_file).expanduser().resolve(),
		nodes=normalize_nodes(args.nodes.split(",") if args.nodes else None),
		start=parse_datetime(args.start),
		end=parse_datetime(args.end),
		resample=args.resample,
		output=Path(args.output).expanduser().resolve(),
	)
	try:
		output_path = export_node_timeseries(config)
	except (ExportError, FileNotFoundError, OSError, ValueError) as exc:
		print(f"Error: {exc}", file=sys.stderr)
		return 2
	print(f"Exported {config.out_file} -> {output_path}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
