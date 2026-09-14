#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 rate_<case>.json 生成"不含汇水区地表蓄水（without_sub）"的 rate 文件。

背景
----
tools/swmm_rpt.py 生成的 rate 表中，每个点的水量构成为：

    total_volume_m3 = 节点累计溢流量 + 节点累计排放量 + Σ(该点关联汇水区的地表蓄水量)
    rate            = total_volume_m3 / (sim_hours * 3600)      # m3/s

本脚本去掉其中的 **汇水区地表蓄水量（subcatchment surface storage）** 这一项，
即只保留 .rpt 里能直接读到的两部分水量：

    total_volume_m3 = Σ original.outfall_flows[].total_volume        (10^6 ltr -> m3)
                    + Σ original.node_flooding[].total_flood_volume  (10^6 ltr -> m3)
    rate            = total_volume_m3 / (sim_hours * 3600)           # m3/s

口径与约定
----------
* sim_hours 取自 original.sim_hours。
* .rpt 的体积列单位是 10^6 ltr（百万升），1 百万升 = 1000 m3，故先 ×1000 换成 m3
  再除以 sim_hours*3600，结果才是 m3/s。
* 输出哪些点、按什么顺序、坐标是什么，**完全沿用原 JSON 的 rate 表**
  （node + coordinate 都从 rate 表里取），只把 rate 换成新算的值。
* 同名节点若同时出现在 outfall_flows 与 node_flooding 中，两部分水量相加。
* outfall_flows 里的 "System" 汇总行是系统总量而不是节点，忽略。
* 在两张表里都查不到的 rate 表节点，rate 记为 0.0（不会丢点、不会补零掩盖）。
* rate 保留 6 位小数，与 tools/swmm_rpt.py 的既有精度一致。
* 输出文件只含一个 "rate" 键，结构为：
      {"rate": [{"node": "J236", "rate": 1.23, "coordinate": [x, y]}, ...]}

用法
----
    python data/export_rate_without_sub.py
    python data/export_rate_without_sub.py data/results/rate_LC_MANUAL_23.json
    python data/export_rate_without_sub.py <in.json> --out <out.json>

默认：data/results/rate_LC_MANUAL_23.json
   -> data/results/rate_LC_MANUAL_23_without_sub.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_M3_PER_1E6_LITRE = 1000.0          # .rpt 体积列 10^6 ltr -> m3
_HOURS_TO_SECONDS = 3600.0          # h -> s
_RATE_DECIMALS = 6                  # rate 输出精度（与 swmm_rpt.py 一致）
_OUTPUT_SUFFIX = "_without_sub"     # 输出文件名后缀

# 仓库根目录（本脚本在 <repo>/data/ 下）
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INPUT = _REPO_ROOT / "data" / "results" / "rate_JJ_MANUAL_7.json"


def default_output_path(input_path: Path) -> Path:
    """在同目录下给文件名主干加 _without_sub 后缀。"""
    return input_path.with_name(f"{input_path.stem}{_OUTPUT_SUFFIX}{input_path.suffix}")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _is_system_row(node: str) -> bool:
    """.rpt 的 Outfall Loading Summary 汇总行（System），不是真实节点。"""
    return node.strip().lower() == "system"


def build_volume_by_node(original: dict) -> dict[str, float]:
    """节点 -> 体积(m3)：outfall 出流量 + 节点溢流量（不含汇水区地表蓄水量）。"""
    volume_by_node: dict[str, float] = {}

    for item in original.get("outfall_flows", []):
        node = item.get("node")
        if not node or _is_system_row(node):
            continue
        volume_by_node[node] = volume_by_node.get(node, 0.0) + float(
            item.get("total_volume", 0.0) or 0.0) * _M3_PER_1E6_LITRE

    for item in original.get("node_flooding", []):
        node = item.get("node")
        if not node or _is_system_row(node):
            continue
        volume_by_node[node] = volume_by_node.get(node, 0.0) + float(
            item.get("total_flood_volume", 0.0) or 0.0) * _M3_PER_1E6_LITRE

    return volume_by_node


def build_without_sub(data: dict) -> tuple[list[dict], dict]:
    """按原 rate 表的点与坐标输出 without_sub 的 rate 列表，并返回统计信息。"""
    original = data.get("original") or {}
    sim_hours = float(original.get("sim_hours") or 0.0)
    if sim_hours <= 0.0:
        raise ValueError(f"original.sim_hours 必须为正数，实际为 {sim_hours!r}")

    seconds = sim_hours * _HOURS_TO_SECONDS
    volume_by_node = build_volume_by_node(original)

    rate_rows: list[dict] = []
    missing: list[str] = []
    zero_nodes: list[str] = []
    matched: OrderedDict[str, float] = OrderedDict()

    for entry in data.get("rate", []):
        node = entry.get("node")
        if node is None:
            continue
        volume_m3 = volume_by_node.get(node, 0.0)
        if node in volume_by_node:
            matched[node] = volume_m3
        else:
            missing.append(node)
        rate = round(volume_m3 / seconds, _RATE_DECIMALS)
        if rate == 0.0:
            zero_nodes.append(node)
        rate_rows.append({
            "node": node,
            "rate": rate,
            "coordinate": entry.get("coordinate"),
        })

    stats = {
        "sim_hours": sim_hours,
        "seconds": seconds,
        "n_rate_nodes": len(rate_rows),
        "n_matched": len(matched),
        "n_missing_in_tables": len(missing),
        "missing_in_tables": missing,
        "n_zero_rate": len(zero_nodes),
        "total_volume_m3": sum(matched.values()),
        "total_rate_m3s": sum(r["rate"] for r in rate_rows),
        # 对照：原 rate 表（含汇水区地表蓄水）的合计
        "old_total_rate_m3s": sum(float(e.get("rate") or 0.0) for e in data.get("rate", [])),
        "n_outfall_rows": len(original.get("outfall_flows", [])),
        "n_flood_rows": len(original.get("node_flooding", [])),
    }
    # 被扣掉的汇水区地表蓄水量（约值：原表的 rate 是 6 位小数舍入后的结果）
    stats["total_surface_storage_m3"] = max(
        0.0, stats["old_total_rate_m3s"] * seconds - stats["total_volume_m3"])
    return rate_rows, stats


def write_output(rate_rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"rate": rate_rows}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=4) + "\n",
                        encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="生成不含汇水区地表蓄水（without_sub）的 rate JSON")
    parser.add_argument("input", nargs="?", default=str(_DEFAULT_INPUT),
                        help=f"输入 rate JSON（默认 {_DEFAULT_INPUT}）")
    parser.add_argument("--out", default=None,
                        help="输出 JSON 路径（默认：输入文件名加 _without_sub 后缀）")
    args = parser.parse_args(argv)

    in_path = Path(args.input).expanduser().resolve()
    if not in_path.is_file():
        print(f"[error] 找不到输入文件：{in_path}", file=sys.stderr)
        return 2
    out_path = (Path(args.out).expanduser().resolve() if args.out
                else default_output_path(in_path))

    print(f"[read ] {in_path}")
    data = load_json(in_path)
    rate_rows, stats = build_without_sub(data)
    write_output(rate_rows, out_path)
    print(f"[write] {out_path}")

    print(f"  sim_hours            : {stats['sim_hours']} h "
          f"({stats['seconds']:.0f} s)")
    print(f"  rate 表点数          : {stats['n_rate_nodes']}")
    print(f"    其中在 outfall/node_flooding 中查到水量 : {stats['n_matched']}")
    print(f"    查不到水量（rate=0，多为纯地表蓄水点）  : {stats['n_missing_in_tables']}")
    if stats["missing_in_tables"]:
        preview = ", ".join(stats["missing_in_tables"][:10])
        more = " ..." if stats["n_missing_in_tables"] > 10 else ""
        print(f"      {preview}{more}")
    print(f"    输出 rate == 0 的点数                   : {stats['n_zero_rate']}")
    print(f"  总水量（不含 sub）   : {stats['total_volume_m3']:,.3f} m3")
    print(f"  Σ rate（不含 sub）   : {stats['total_rate_m3s']:.6f} m3/s")
    print(f"  Σ rate（原表，含 sub）: {stats['old_total_rate_m3s']:.6f} m3/s")
    print(f"  差额（≈Σ 汇水区地表蓄水/时长）: "
          f"{stats['old_total_rate_m3s'] - stats['total_rate_m3s']:.6f} m3/s")
    print(f"  outfall_flows 行数   : {stats['n_outfall_rows']}"
          f"（含 System 汇总行）")
    print(f"  node_flooding 行数   : {stats['n_flood_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
