from __future__ import annotations

"""SWMM 报告解析与速率汇总程序。

该程序接受两个输入文件：
  1. 一个 SWMM 的 .inp 输入文件（用于解析 [OPTIONS] 的模拟起止时间、[COORDINATES]
     的节点坐标、[SUBCATCHMENTS] 的汇水区→出水口映射、[OUTFALLS] 的出水口类型、
     以及 [POLYGONS] 的汇水区多边形）；
  2. 与 .inp 对应的 .rpt 结果报告文件（用于解析排放口出流、节点淹没、
     管段峰值与满流、以及汇水区地表蓄水总量等结果）。

程序**同时生成两个 JSON 文件**作为输出。两个文件结构完全相同（rate + original），
只有 rate 表的计算口径不同，节点清单与坐标完全一致，可以逐点对照：

  data/results/rate_<主干名>.json           # ① 只用 junction 溢流数据算 rate
  data/results/rate_<主干名>_with_sub.json  # ② 溢流 + 出水口出流 + 汇水区地表蓄水

  {
    "rate": [                                  # 计算后的速率信息（合并后的单一列表）
      {"node": "J236", "rate": 1.23, "coordinate": [x, y]},
      {"node": "sea41", "rate": 0.45, "coordinate": [x, y]},
      ...
    ],
    "original": { ... }                        # 原本的解析信息 + 新增的蓄水字段
  }

rate 部分（两套口径，见 original.rate_basis）：两套口径的**节点清单与坐标完全相同**，
唯一区别是「汇水区地表蓄水量算不算进 rate」。两者互补，水量不重不漏。

  * **rate_<主干名>.json**（rate_basis = "without_subcatchment_storage"，主口径）——
    **不含汇水区地表蓄水**：rate = (该节点累计溢流量 + 该节点排放口排放量) / (sim_hours*3600)
      - 溢流量取 .rpt 的 Node Flooding Summary（体积列 10^6 ltr -> m3），即节点漫出的水；
      - 排放量取 Outfall Loading Summary 的 Total Volume，即 sea*/mount* 排走的水；
      - **留在汇水区地表的水（Final Storage）不在这里算**，它由虚拟降雨雨型
        chi_<主干名>.txt 代表（见 main.py）。因此「Σ rate × 模拟时长 + 面雨总量」
        正好等于全部水量，既不会像"只算 junction 溢流"那样漏掉 sea*/mount* 的排放量，
        也不会和虚拟降雨重复计算。
  * **rate_<主干名>_with_sub.json**（rate_basis = "with_subcatchment_storage"）——
    **含汇水区地表蓄水**（"把留在汇水区的水量加到溢流上"的口径）：
        rate = (该节点累计溢流量 + 该节点累计排放量 + Σ关联汇水区地表蓄水量)
               / (sim_hours * 3600)
      即本模块的历史口径，**与旧版 rate JSON 完全一致**。

rate 表的节点清单（两个文件相同）：
  * **rate 表里的点全部是"虚拟出水口"**。判定口径：
      只要被汇水区在 [SUBCATCHMENTS] 的 Outlet 列点到名，就视为虚拟出水口，
      不管它是 J* / sea* / mount* / vir* / out* 中的哪一种；
      另外 [OUTFALLS] 里名字以 sea* / mount* / vir* 开头的也按其命名视为虚拟出水口。
      此外，**未被指定但有节点溢流**的节点也会纳入 rate，以免丢掉那部分溢流水量
      （这些点会在 meta.n_flood_only_nodes_in_rate 里单独说明）。
  * 真正的"实际排放口"（[OUTFALLS] 里，既未被任何汇水区指定为 Outlet、
    名字也不是 sea*/mount*/vir*）**不进入 rate 表**；其原始出流仍完整保留在
    original.outfall_flows，逐个明细见 original.excluded_real_outfalls。
    如需把全部实际排放口也放进 rate，用 include_real_outfalls=True /
    命令行 --include-real-outfalls。
  * total_volume(m3) = 该节点的累计溢流量
                     + 该节点的累计排放量（若它是 Outfall）
                     + Σ(该节点作为 Outlet 关联的**所有**汇水区地表蓄水量)
  * rate = total_volume / (sim_hours * 3600)（total_volume 与 rate 说的是 with_sub 口径；
                                           不含蓄水口径 = total_volume - 汇水区地表蓄水量），单位 m3/s
  * coordinate 来自 .inp 的 [COORDINATES]；若虚拟出水口没有坐标，则回退到
    其关联汇水区多边形的质心（见 _resolve_virtual_outfall_coordinate），
    仍取不到时输出 null 并在日志中说明。
  * 历史上 rate 里分开的 outflows / nodeflooding 两个列表已合并为本列表；
    它们的原始明细仍完整保留在 original.outfall_flows / original.node_flooding 中。

【汇水区地表蓄水量（surface storage）如何取得 —— 重要说明】
  SWMM 的 Runoff Quantity Continuity 里的 “Final Storage” 就是全部汇水区在模拟
  结束时刻仍滞留在地表、尚未进入管网的水量。但它只有**总量**，官方工具包
  （.out 的 SubcatchAttribute、引擎的 SubcatchResult、subcatch_get_stats）都
  **不提供单个汇水区的地表蓄水**；SWMM 的 hotstart 文件实测也不含该状态
  （1158x20 的子汇水区块与 919x2 的节点块在整段模拟后仍全为 0）。
  因此本程序采用**质量平衡反推**（这是唯一可行的、非伪造的做法）：

      storage_i = precip_i + runon_i - evap_i - infil_i - runoff_i

  其中 precip/runon/evap/infil/runoff 全部来自官方引擎 API
  swmm_toolkit.solver.subcatch_get_stats(i)，需要按 .inp 复算一次（约数秒）。
  各字段单位不统一（实测 precip 是 mm 深度，infil/runoff 是 m3 体积），
  程序会用 .rpt 里的已知总量自动判定，不会写死。
  反推得到的 Σstorage 与 .rpt 的 Final Storage 之间恰差一个 Runoff 连续性误差，
  程序默认按比例缩放到 .rpt 的官方总量（scale_to_reported=True），
  并在输出中同时保留未缩放的 raw 值，绝不填 0 掩盖缺失。

original 部分除保留 parse_report() 解析出的全部原始信息（流量单位、连续性误差、
淹没损失、outfall_flows / node_flooding / link_peak_flows / conduit_surcharge 明细等）
外，还会额外补充：
  * inp_path、起止日期/时间、sim_hours（总模拟时长，小时）
  * 完整坐标映射 coordinates（供下游直接使用，无需再读 .inp）
  * outfall_flows / node_flooding 中每一条新增 surface_storage_m3 字段
  * outlet_storage：逐出水口的汇总（构成明细，便于核对）
  * subcatch_surface_storage：逐汇水区的地表蓄水量明细（可追溯，不造假）
  * surface_storage_meta：取数方法、总量核对、缩放系数、告警，
    以及本文件用的 rate 口径（rate_basis / rate_basis_note / rate_basis_volume_in_rate_m3）
  * subcatchment_outlets：汇水区 -> 出水口的映射

命令行接口（以下三种等价）：
  python tools/swmm_rpt.py <inp> <rpt> [--out <json路径>]
  python -m tools.swmm_rpt <inp> [<rpt>] [--out <json路径>]
  python tools/swmm_rpt.py <inp>            # 自动使用同目录同名 .rpt

默认输出位置为 tools/config.py 中的 RESULTS_DIR，**一次写两个文件**：
  rate_<原inp文件主干名>.json           —— 不含汇水区地表蓄水（溢流 + 出水口排放量）
  rate_<原inp文件主干名>_with_sub.json  —— 加上 Σ关联汇水区地表蓄水量
例如 data/results/rate_LC_MANUAL_23.json 与 rate_LC_MANUAL_23_with_sub.json。
--out 给出的是**前一个**的路径，后一个由它派生（主干名后加 _with_sub）。

Python 调用接口：
  from tools.swmm_rpt import (build_output_data, build_output_data_from_bundle,
                              prepare_report_bundle, write_output_file,
                              write_output_files)
  data = build_output_data("xxx.inp", "xxx.rpt")            # -> dict（默认 with_sub 口径）
  data = build_output_data("xxx.inp", "xxx.rpt",
                           rate_basis="without_subcatchment_storage")  # -> 不含蓄水口径
  paths = write_output_files("xxx.inp", "xxx.rpt")          # -> (不含蓄水, 蓄水)
  # 想只复算一次地表蓄水量、却要两种口径的 dict：
  bundle = prepare_report_bundle("xxx.inp", "xxx.rpt")
  d1 = build_output_data_from_bundle(bundle, rate_basis="without_subcatchment_storage")
  d2 = build_output_data_from_bundle(bundle, rate_basis="with_subcatchment_storage")

说明与约定：
  * 报告中的体积列单位是 10^6 ltr（百万升），1 百万升 = 1000 立方米；
    程序内部统一换算为 m3 后再相加，并在字段名/注释里显式标注单位。
  * Outfall Loading Summary 中的 System 汇总行会保留在 original.outfall_flows 中，
    但**不会**进入 rate 列表（它是总量，不是节点）。
  * 速率默认保留 6 位小数（不会过度舍入），如需 float 原始精度可将
    模块常量 _RATE_DECIMALS 改为 None。
  * 当 .inp 中某节点没有坐标（或坐标段缺失）时 coordinate 为 null。
  * 若汇水区的 Outlet 指向**另一个汇水区**（SWMM 允许串联），程序会沿着链条
    走到最终的节点出水口，并在 surface_storage_meta.warnings 中记录。
"""

import argparse
import json
import re
import sys
import tempfile
from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path

try:
    # 以模块方式运行（python -m tools.swmm_rpt / 被 import）时走这里。
    from tools.config import RESULTS_DIR, SWMM_DATA_DIR
except ImportError:  # pragma: no cover - 直接 python tools/swmm_rpt.py 运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools.config import RESULTS_DIR, SWMM_DATA_DIR


# ---------------------------------------------------------------------------
# RPT 原始解析的数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutfallFlow:
    """单个 Outfall（含 System 行）的出流汇总。(Outfall Loading Summary)"""

    node: str
    flow_frequency: float
    average_flow: float
    maximum_flow: float
    total_volume: float


@dataclass(frozen=True)
class NodeFlooding:
    """单个节点的淹没（溢流）汇总。(Node Flooding Summary)"""

    node: str
    hours_flooded: float
    maximum_rate: float
    time_of_max: str
    total_flood_volume: float
    maximum_ponded_volume: float


@dataclass(frozen=True)
class LinkPeakFlow:
    """单条管段（Link）的峰值流量与能力比指标。(Link Flow Summary)"""

    link: str
    link_type: str
    maximum_flow: float
    time_of_max: str
    maximum_velocity: float
    max_full_flow: float
    max_full_depth: float


@dataclass(frozen=True)
class ConduitSurcharge:
    """单条管段的满流/超载时长统计。(Conduit Surcharge Summary)"""

    conduit: str
    hours_full_both_ends: float
    hours_full_upstream: float
    hours_full_downstream: float
    hours_above_full_normal_flow: float
    hours_capacity_limited: float


@dataclass(frozen=True)
class SubcatchmentInfo:
    """[SUBCATCHMENTS] 的一行。

    outlet 可能是：
      * 一个节点名（J236 / sea41 / mount3 / out1 ...）
      * 另一个子汇水面积名（SWMM 允许汇水区串联，此时需沿链走到最终节点）
    """

    name: str
    raingage: str
    outlet: str
    area_ha: float
    pct_imperv: float
    width: float
    slope: float
    curb_len: float


@dataclass(frozen=True)
class OutfallInfo:
    """[OUTFALLS] 的一行。

    is_virtual 按命名约定判定：以 sea / mount 开头的出水口视为“虚拟出水口”，
    代表那些附近没有管线的汇水区的出水点（见模块 docstring）。
    """

    name: str
    elevation: float
    kind: str            # FREE / NORMAL / FIXED / TIDAL / TIMESERIES
    is_virtual: bool


@dataclass(frozen=True)
class SubcatchmentStorage:
    """单个汇水区在模拟结束时刻的地表蓄水量（质量平衡反推）。

    单位统一为 m3 / mm。storage_raw_m3 是直接反推值，storage_m3 是按
    .rpt 官方总量缩放后的值（scale_to_reported=True 时二者不同）。
    """

    name: str
    outlet: str
    area_m2: float
    precip_m3: float
    runon_m3: float
    evap_m3: float
    infil_m3: float
    runoff_m3: float
    storage_raw_m3: float
    storage_m3: float
    storage_depth_mm: float


@dataclass(frozen=True)
class SurfaceStorageResult:
    """全部汇水区地表蓄水量的取数结果（含方法、核对与告警）。"""

    method: str
    per_subcatchment: tuple[SubcatchmentStorage, ...]
    raw_total_m3: float
    reported_total_m3: float | None
    scale_factor: float
    total_area_m2: float
    unit_choices: dict
    warnings: tuple[str, ...]
    engine_note: str

    def by_name(self) -> dict[str, SubcatchmentStorage]:
        return {item.name: item for item in self.per_subcatchment}


@dataclass(frozen=True)
class OutletAggregate:
    """按出水口节点汇总后的水量构成（全部单位 m3，rate 为 m3/s）。

    两套 rate 口径**同时**保留，具体输出哪一套由调用方（rate_basis）决定：
      * rate_without_sub = (该节点溢流量 + 该节点排放口出流量) / (sim_hours*3600)
      * rate_with_sub    = 上面两项 + Σ关联汇水区地表蓄水量，再除以时间
    """

    node: str
    node_class: str                 # junction / outfall / other
    is_virtual_outfall: bool
    coordinate: list[float] | None
    coordinate_source: str
    subcatchments: tuple[str, ...]
    surface_storage_m3: float
    node_flood_volume_m3: float
    outfall_outflow_m3: float
    total_volume_m3: float
    # 主口径参与 rate 的水量 = 溢流量 + 出水口排放量 = total - 汇水区地表蓄水。
    without_sub_volume_m3: float
    # 其中溢流发生在**非** junction 节点的部分（信息用：本项目的案例里为 0）。
    nonjunction_flood_volume_m3: float
    rate_with_sub: float
    rate_without_sub: float

    # ---- 口径选择 ----
    @property
    def rate(self) -> float:
        """向后兼容旧字段：等价于 rate_with_sub（历史口径）。"""
        return self.rate_with_sub

    def rate_for(self, rate_basis: str) -> float:
        """按口径取 rate（m3/s）。"""
        return (self.rate_without_sub if check_rate_basis(rate_basis)
                == RATE_BASIS_WITHOUT_SUB else self.rate_with_sub)

    def rate_volume_m3_for(self, rate_basis: str) -> float:
        """按口径取参与 rate 计算的水量（m3）。"""
        return (self.without_sub_volume_m3 if check_rate_basis(rate_basis)
                == RATE_BASIS_WITHOUT_SUB else self.total_volume_m3)


@dataclass(frozen=True)
class SwmmReportSummary:
    """RPT 解析结果（当前聚焦三类流量）。"""

    report_path: Path
    flow_unit: str

    # 系统级关键数值，方便先做总量汇报或快速质检。
    runoff_continuity_error: float
    routing_continuity_error: float
    flooding_loss_volume: float
    flooding_loss_volume_secondary: float

    # 三类流量的对象级明细。
    outfall_flows: list[OutfallFlow]
    node_flooding: list[NodeFlooding]
    link_peak_flows: list[LinkPeakFlow]
    conduit_surcharge: list[ConduitSurcharge]

    # 兼容旧代码中的字段命名，避免 test.py 或下游调用立刻改动。
    @property
    def flooded_nodes(self) -> list[NodeFlooding]:
        return self.node_flooding

    @property
    def system_outfall_total_volume(self) -> float:
        for item in self.outfall_flows:
            if item.node.strip().lower() == "system":
                return item.total_volume
        return 0.0

    @property
    def system_peak_outfall_flow(self) -> float:
        for item in self.outfall_flows:
            if item.node.strip().lower() == "system":
                return item.maximum_flow
        return 0.0

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["report_path"] = str(self.report_path)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 通用文本读取：兼容 UTF-8 / GBK 等编码，避免 Windows 平台中文注释乱码
# ---------------------------------------------------------------------------


def _read_text_file(path: Path) -> str:
    """读取文本文件，自动尝试常见编码（utf-8-sig / utf-8 / gb18030）。"""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# INP 解析：[OPTIONS] 起止时间 / 总时长，[COORDINATES] 节点坐标
# ---------------------------------------------------------------------------


def parse_inp_options(text: str) -> dict[str, str]:
    """解析 INP 中 [OPTIONS] 部分的键值对。

    忽略空行与以 ';' 开头的注释行，键统一转为大写
    （如 START_DATE / START_TIME / END_DATE / END_TIME）。
    """
    options: dict[str, str] = {}
    in_options = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_options = line[1:-1].strip().upper() == "OPTIONS"
            continue
        if not in_options:
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            options[parts[0].upper()] = parts[1].strip()
    return options


def compute_sim_hours(options: dict[str, str]) -> tuple[datetime, datetime, float]:
    """根据 [OPTIONS] 的起止日期时间计算总模拟时长（小时）。

    Returns:
        (start_datetime, end_datetime, sim_hours)

    Raises:
        ValueError: 缺少起止字段、日期格式错误或时长不为正时抛出。
    """
    required = ("START_DATE", "START_TIME", "END_DATE", "END_TIME")
    missing = [key for key in required if key not in options]
    if missing:
        raise ValueError(f"[OPTIONS] missing fields: {', '.join(missing)}")

    try:
        start = datetime.strptime(
            f"{options['START_DATE']} {options['START_TIME']}", "%m/%d/%Y %H:%M:%S"
        )
        end = datetime.strptime(
            f"{options['END_DATE']} {options['END_TIME']}", "%m/%d/%Y %H:%M:%S"
        )
    except ValueError as exc:
        raise ValueError(
            "Cannot parse START/END date-time from [OPTIONS]; "
            f"expect MM/DD/YYYY HH:MM:SS, got: "
            f"{options['START_DATE']} {options['START_TIME']} -> "
            f"{options['END_DATE']} {options['END_TIME']}"
        ) from exc

    sim_hours = (end - start).total_seconds() / 3600.0
    if sim_hours <= 0:
        raise ValueError(
            f"Simulation duration must be positive, got {sim_hours} hours "
            f"({options['START_DATE']} {options['START_TIME']} -> "
            f"{options['END_DATE']} {options['END_TIME']})."
        )
    return start, end, sim_hours


def parse_inp_coordinates(text: str) -> dict[str, list[float]]:
    """解析 INP 中 [COORDINATES] 部分的节点坐标。

    每行格式为「节点名 X Y」，忽略空行与 ';' 开头的注释行。
    返回 {节点名: [X, Y]}，坐标以 float 保留原精度。
    """
    coordinates: dict[str, list[float]] = {}
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_section = line[1:-1].strip().upper() == "COORDINATES"
            continue
        if not in_section:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        name, x_text, y_text = parts[0], parts[1], parts[2]
        try:
            coordinates[name] = [float(x_text), float(y_text)]
        except ValueError:
            # 非坐标行（例如其他列被误判），跳过即可。
            continue
    return coordinates


# ---------------------------------------------------------------------------
# INP 解析：[SUBCATCHMENTS] / [OUTFALLS] / [JUNCTIONS] / [POLYGONS]
# ---------------------------------------------------------------------------


def _iter_inp_section_rows(text: str, section: str):
    """逐行产出 [SECTION] 下的数据行（已去注释、去空行、按空白切分）。"""
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.split(";")[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            in_section = line[1:-1].strip().upper() == section.upper()
            continue
        if in_section:
            yield line.split()


def _to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_inp_subcatchments(text: str) -> list[SubcatchmentInfo]:
    """解析 [SUBCATCHMENTS]，建立汇水区清单及其出水口（Outlet）映射。

    列序：Name RainGage Outlet Area %Imperv Width %Slope CurbLen [SnowPack]
    """
    items: list[SubcatchmentInfo] = []
    for parts in _iter_inp_section_rows(text, "SUBCATCHMENTS"):
        if len(parts) < 6:
            continue
        items.append(
            SubcatchmentInfo(
                name=parts[0],
                raingage=parts[1],
                outlet=parts[2],
                area_ha=_to_float(parts[3]),
                pct_imperv=_to_float(parts[4]),
                width=_to_float(parts[5]),
                slope=_to_float(parts[6]) if len(parts) > 6 else 0.0,
                curb_len=_to_float(parts[7]) if len(parts) > 7 else 0.0,
            )
        )
    return items


def parse_inp_outfalls(text: str) -> list[OutfallInfo]:
    """解析 [OUTFALLS]，标出哪些是虚拟出水口（sea* / mount*）。

    列序：Name Elevation Type [StageData Gated RouteTo]
    """
    items: list[OutfallInfo] = []
    for parts in _iter_inp_section_rows(text, "OUTFALLS"):
        if len(parts) < 3:
            continue
        name = parts[0]
        items.append(
            OutfallInfo(
                name=name,
                elevation=_to_float(parts[1]),
                kind=parts[2].upper(),
                is_virtual=is_virtual_outfall_name(name),
            )
        )
    return items


def parse_inp_junctions(text: str) -> list[str]:
    """解析 [JUNCTIONS] 的节点名。"""
    return [parts[0] for parts in _iter_inp_section_rows(text, "JUNCTIONS") if parts]


def parse_inp_polygons(text: str) -> dict[str, list[list[float]]]:
    """解析 [POLYGONS]，返回 {汇水区名: [[x, y], ...]}（用于质心回退）。"""
    polygons: dict[str, list[list[float]]] = OrderedDict()
    for parts in _iter_inp_section_rows(text, "POLYGONS"):
        if len(parts) < 3:
            continue
        try:
            x, y = float(parts[1]), float(parts[2])
        except ValueError:
            continue
        polygons.setdefault(parts[0], []).append([x, y])
    return polygons


# 虚拟出水口的命名约定（按名字识别的虚拟出水口：sea* / mount* / vir*）
VIRTUAL_OUTFALL_PREFIXES: tuple[str, ...] = ("sea", "mount", "vir")


def is_virtual_outfall_name(name: str) -> bool:
    """按命名约定判断是否虚拟出水口（sea1 / mount12 / vir3 ...）。

    注意：这只是**按名字**识别。最终"是不是虚拟出水口"的判据见
    build_outlet_aggregates()：**只要被汇水区在 [SUBCATCHMENTS] 的 Outlet 列
    指定，就一律视为虚拟出水口**，不管它叫什么名字。
    """
    low = name.strip().lower()
    return any(low == p or low.startswith(p) for p in VIRTUAL_OUTFALL_PREFIXES)


def classify_node_name(name: str) -> str:
    """按命名约定粗分节点类型：junction / outfall / other。"""
    if re.match(r"^[Jj]\d+$", name):
        return "junction"
    if is_virtual_outfall_name(name):
        return "outfall"
    if re.match(r"^(out|O)\d+$", name):
        return "outfall"
    return "other"


def polygon_centroid(points: list[list[float]]) -> list[float] | None:
    """多边形质心（用顶点平均值近似；取不到顶点时返回 None）。"""
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [sum(xs) / len(xs), sum(ys) / len(ys)]


# ---------------------------------------------------------------------------
# 汇水区地表蓄水量：质量平衡反推（官方 API 不直接提供，详见模块 docstring）
# ---------------------------------------------------------------------------


class SurfaceStorageError(ValueError):
    """汇水区地表蓄水量无法取得时抛出（绝不静默填 0）。

    继承 ValueError 是为了与既有调用方（例如 main.py 里的
    `except (FileNotFoundError, ValueError)`）保持兼容，让上层能给出干净的
    错误信息而不是抛栈。
    """


_FT3_TO_M3 = 0.028316846592
_M3_PER_HECTARE_M = 10_000.0


def _reported_runoff_final_storage(rpt_text: str) -> tuple[float | None, float | None]:
    """从 .rpt 的 Runoff Quantity Continuity 取官方 Final Storage。

    返回 (hectare-m, mm)。
    """
    m = re.search(
        r"Final Storage\s*\.{2,}\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)",
        rpt_text,
    )
    if not m:
        return (None, None)
    return (float(m.group(1)), float(m.group(2)))


def read_runoff_final_storage(
    rpt_path: str | Path,
) -> tuple[float | None, float | None]:
    """读取 .rpt 的 Runoff Quantity Continuity -> Final Storage。

    Returns:
        (hectare-m, mm)：官方报告的同一份水量的两种单位；
        报告中找不到该行时返回 (None, None)（不猜、不填 0）。

    该值同时是：
      * 汇水区地表蓄水量反推值的缩放目标（compute_surface_storage）；
      * 虚拟降雨雨型（tools/get_chi.py 生成的 chi_<主干名>.txt）的雨量。
    """
    path = Path(rpt_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Invalid report file: {path}")
    return _reported_runoff_final_storage(_read_text_file(path))


def _pick_writable_dir(inp_path: Path) -> Path:
    """挑一个真的能写的临时目录。

    注意：不能盲目用 tempfile.gettempdir()——在受限环境下（例如沙箱、只读
    临时目录、企业策略）SWMM 会因为写不出报告文件而报 ERROR 305。
    这里逐个候选目录做一次真实写入测试，选第一个可用的。
    """
    candidates = [
        Path(tempfile.gettempdir()) / "swmm_rpt",
        Path.cwd() / ".swmm_rpt_tmp",
        inp_path.parent / ".swmm_rpt_tmp",
    ]
    for base in candidates:
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return base
        except OSError:
            continue
    raise SurfaceStorageError(
        "找不到可写的临时目录（SWMM 复算需要写出 .rpt/.out）。"
        f"已尝试：{[str(c) for c in candidates]}。"
        "请用 workdir= 参数显式指定一个可写目录。"
    )


def compute_surface_storage(
    inp_path: str | Path,
    rpt_path: str | Path,
    *,
    scale_to_reported: bool = True,
    workdir: str | Path | None = None,
) -> SurfaceStorageResult:
    """按 .inp 复算一次 SWMM，用质量平衡反推每个汇水区的地表蓄水量。

    反推公式（全部为官方引擎 API subcatch_get_stats 的字段）：
        storage_i = precip_i + runon_i - evap_i - infil_i - runoff_i

    各字段单位并不统一，程序用 .rpt 里的已知总量自动判定（不写死）：
        * precip 实测是「深度 mm」，需 x area / 1000 才是 m3
        * infil / runoff 实测是「体积 m3」
        * evap / runon 在本模型为 0，无法判定时按体积处理并记录告警
    """
    try:
        from swmm.toolkit import solver as _solver, shared_enum as _se
    except ImportError as exc:  # pragma: no cover
        raise SurfaceStorageError(
            "无法取得汇水区地表蓄水量：缺少 swmm-toolkit（官方 SWMM Toolkit 的 "
            "Python 绑定）。请先 pip install swmm-toolkit，或显式关闭该功能"
            "（surface_storage='off'），否则 rate 会缺少“地表蓄水”这一部分。"
        ) from exc

    inp_path = Path(inp_path).expanduser().resolve()
    rpt_path = Path(rpt_path).expanduser().resolve()
    if not inp_path.exists():
        raise SurfaceStorageError(f".inp 不存在，无法复算：{inp_path}")
    rpt_text = _read_text_file(rpt_path) if rpt_path.exists() else ""

    inp_text = _read_text_file(inp_path)
    subcatchments = parse_inp_subcatchments(inp_text)
    if not subcatchments:
        raise SurfaceStorageError(f"[SUBCATCHMENTS] 为空或解析失败：{inp_path}")
    area_m2 = {s.name: s.area_ha * _M3_PER_HECTARE_M for s in subcatchments}
    total_area_m2 = sum(area_m2.values())

    warnings: list[str] = []
    cleanup_dir: Path | None = None
    if workdir is None:
        workdir = _pick_writable_dir(inp_path)
        cleanup_dir = workdir
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    tmp_rpt = workdir / "surface_storage.rpt"
    tmp_out = workdir / "surface_storage.out"
    for f in (tmp_rpt, tmp_out):
        try:
            if f.exists():
                f.unlink()
        except OSError:
            pass

    engine_note = ""
    try:
        err = _solver.swmm_open(str(inp_path), str(tmp_rpt), str(tmp_out))
        if err:
            raise SurfaceStorageError(f"swmm_open 失败 (err={err})：{inp_path}")
        _solver.swmm_start(0)
        try:
            while _solver.swmm_step():
                pass
            n_sub = _solver.project_get_count(_se.ObjectType.SUBCATCH)
            names = [_solver.project_get_id(_se.ObjectType.SUBCATCH, i)
                     for i in range(n_sub)]
            raw = {}
            for i, nm in enumerate(names):
                st = _solver.subcatch_get_stats(i)
                raw[nm] = {
                    "precip": float(st.precip), "runon": float(st.runon),
                    "evap": float(st.evap), "infil": float(st.infil),
                    "runoff": float(st.runoff),
                }
            engine_note = f"引擎版本 {_solver.swmm_version_info()}"
        finally:
            try:
                _solver.swmm_end()
            except Exception:
                pass
            try:
                _solver.swmm_close()
            except Exception:
                pass
    except SurfaceStorageError:
        raise
    except Exception as exc:  # pragma: no cover
        raise SurfaceStorageError(
            f"复算 SWMM 以取得汇水区蓄水失败：{exc!r}（工作目录 {workdir}）") from exc
    finally:
        if cleanup_dir is not None:
            for f in (tmp_rpt, tmp_out):
                try:
                    if f.exists():
                        f.unlink()
                except OSError:
                    pass
            try:
                cleanup_dir.rmdir()
            except OSError:
                pass

    missing = [s.name for s in subcatchments if s.name not in raw]
    if missing:
        raise SurfaceStorageError(
            f"{len(missing)} 个汇水区在复算结果中找不到（例如 {missing[:5]}），"
            "无法给出其地表蓄水量；已中止而不是填 0。"
        )

    # ---- 逐字段单位判定（与 .rpt 已知总量比对）----
    def rpt_total_m3(label: str) -> float | None:
        m = re.search(rf"{re.escape(label)}\s*\.{{2,}}\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)",
                      rpt_text)
        return float(m.group(1)) * _M3_PER_HECTARE_M if m else None

    known = {
        "precip": rpt_total_m3("Total Precipitation"),
        "infil": rpt_total_m3("Infiltration Loss"),
        "runoff": rpt_total_m3("Surface Runoff"),
        "evap": rpt_total_m3("Evaporation Loss"),
        "runon": 0.0,
    }
    unit_choices: dict[str, dict] = {}
    for key in ("precip", "infil", "runoff", "evap", "runon"):
        as_volume = sum(raw[n][key] for n in raw)
        as_depth = sum(raw[n][key] / 1000.0 * area_m2.get(n, 0.0) for n in raw)
        ref = known.get(key)
        if ref is None:
            choice, err_pct = "体积_m3", None
            warnings.append(f"{key}: .rpt 中没有对应总量，无法判定字段单位，按体积(m3)处理。")
        else:
            d_vol = abs(as_volume - ref)
            d_dep = abs(as_depth - ref)
            if max(as_volume, as_depth, ref) <= 0.0:
                choice, err_pct = "体积_m3", 0.0
            elif d_vol <= d_dep:
                choice, err_pct = "体积_m3", (100.0 * (as_volume - ref) / ref if ref else None)
            else:
                choice, err_pct = "深度_mm->m3", (100.0 * (as_depth - ref) / ref if ref else None)
            if err_pct is not None and abs(err_pct) > 1.0:
                warnings.append(
                    f"{key}: 换算后与 .rpt 总量仍差 {err_pct:+.2f}% "
                    f"(复算引擎与生成 .rpt 的引擎可能不是同一构建)。")
        unit_choices[key] = {"单位判定": choice, "按体积汇总_m3": as_volume,
                             "按深度汇总_m3": as_depth, "rpt对应总量_m3": ref,
                             "相对偏差_pct": err_pct}

    def to_m3(name: str, key: str) -> float:
        v = raw[name][key]
        if unit_choices[key]["单位判定"] == "体积_m3":
            return v
        return v / 1000.0 * area_m2.get(name, 0.0)

    per: list[SubcatchmentStorage] = []
    raw_total = 0.0
    for s in subcatchments:
        pm = to_m3(s.name, "precip")
        rm = to_m3(s.name, "runon")
        em = to_m3(s.name, "evap")
        im = to_m3(s.name, "infil")
        om = to_m3(s.name, "runoff")
        residual = pm + rm - em - im - om
        raw_total += residual
        per.append(
            SubcatchmentStorage(
                name=s.name, outlet=s.outlet, area_m2=area_m2.get(s.name, 0.0),
                precip_m3=pm, runon_m3=rm, evap_m3=em, infil_m3=im, runoff_m3=om,
                storage_raw_m3=residual, storage_m3=residual,
                storage_depth_mm=(residual / area_m2[s.name] * 1000.0
                                  if area_m2.get(s.name) else 0.0),
            )
        )

    ha_m, mm = _reported_runoff_final_storage(rpt_text)
    reported_total = (mm / 1000.0 * total_area_m2) if mm is not None else None
    scale = 1.0
    if scale_to_reported and reported_total and raw_total > 0.0:
        scale = reported_total / raw_total
        if abs(scale - 1.0) > 0.02:
            warnings.append(
                f"反推总量 {raw_total:,.1f} m3 与 .rpt 官方 Final Storage "
                f"{reported_total:,.1f} m3 相差 {100 * (scale - 1):+.2f}%，"
                "差额主要来自 Runoff 连续性误差（SWMM 把水量不平衡整体记在 Final Storage 上）。"
                "已按比例缩放到官方总量；未缩放的原始值保留在 storage_raw_m3 / "
                "surface_storage_meta.raw_total_m3_m3 中。")
        per = [replace(x, storage_m3=x.storage_raw_m3 * scale,
                       storage_depth_mm=(x.storage_raw_m3 * scale / x.area_m2 * 1000.0
                                         if x.area_m2 else 0.0))
               for x in per]
    elif scale_to_reported and reported_total is None:
        warnings.append("未能在 .rpt 中找到 Runoff Quantity Continuity 的 Final Storage，"
                        "未做缩放，直接使用反推值。")

    return SurfaceStorageResult(
        method="mass_balance(subcatch_get_stats)",
        per_subcatchment=tuple(per),
        raw_total_m3=raw_total,
        reported_total_m3=reported_total,
        scale_factor=scale,
        total_area_m2=total_area_m2,
        unit_choices=unit_choices,
        warnings=tuple(warnings),
        engine_note=engine_note,
    )


# ---------------------------------------------------------------------------
# 出水口聚合：汇水区 -> 出水口（含汇水区串联的处理）
# ---------------------------------------------------------------------------


def build_outlet_map(
    subcatchments: list[SubcatchmentInfo],
    node_names: set[str],
) -> tuple[OrderedDict[str, list[str]], list[str]]:
    """建立 出水口节点 -> 汇水区列表 的映射。

    处理三类 Outlet：
      * 节点名（J*/sea*/mount*/out*）—— 直接用
      * 另一个汇水区名 —— SWMM 允许串联，沿链走到最终节点，把水量归到最终下游出水口
      * 既不是节点也不是汇水区 —— 记录告警
    返回 (映射, 告警列表)。
    """
    by_name = {s.name: s for s in subcatchments}
    warnings: list[str] = []
    mapping: OrderedDict[str, list[str]] = OrderedDict()

    def resolve(start: SubcatchmentInfo) -> str | None:
        seen = [start.name]
        cur = start.outlet
        for _ in range(64):
            if cur in node_names:
                return cur
            if cur in by_name:
                if cur in seen:
                    warnings.append(
                        f"汇水区 {start.name} 的 Outlet 链条出现环 "
                        f"({' -> '.join(seen + [cur])})，已跳过。")
                    return None
                seen.append(cur)
                cur = by_name[cur].outlet
                continue
            return None
        warnings.append(f"汇水区 {start.name} 的 Outlet 链条过长，已跳过。")
        return None

    for s in subcatchments:
        target = resolve(s)
        if target is None:
            warnings.append(
                f"汇水区 {s.name} 的 Outlet='{s.outlet}' 既不是节点也不是汇水区，"
                "该汇水区的地表蓄水量无法归属，已跳过（不计入任何出水口）。")
            continue
        if s.outlet != target:
            warnings.append(
                f"汇水区 {s.name} 的 Outlet='{s.outlet}' 指向另一个汇水区，"
                f"已沿链归到最终下游出水口 '{target}'。")
        mapping.setdefault(target, []).append(s.name)

    # 一个汇水区只能有一个出水口：这里天然成立，但做一次防御性检查
    seen_sub = Counter(nm for v in mapping.values() for nm in v)
    dup = [nm for nm, c in seen_sub.items() if c > 1]
    if dup:
        warnings.append(f"有 {len(dup)} 个汇水区被关联到多个出水口：{dup[:5]}（请检查 .inp）。")
    return mapping, warnings


def _resolve_virtual_outfall_coordinate(
    outlet: str,
    coordinates: dict[str, list[float]],
    subcatchments: list[str],
    polygons: dict[str, list[list[float]]],
) -> tuple[list[float] | None, str]:
    """虚拟出水口的坐标回退方案。

    顺序：1) [COORDINATES] 里直接有；2) 关联汇水区多边形的加权质心；
          3) 关联汇水区出口节点的坐标；4) None。
    """
    if outlet in coordinates:
        return coordinates[outlet], "coordinates"
    pts = []
    for nm in subcatchments:
        c = polygon_centroid(polygons.get(nm, []))
        if c:
            pts.append(c)
    if pts:
        return ([sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)],
                "polygon_centroid")
    return None, "none"


@dataclass(frozen=True)
class SwmmInpData:
    """从 INP 中提取的模拟元信息。"""

    path: Path
    options: dict[str, str]                       # [OPTIONS] 原始键值
    start: datetime
    end: datetime
    sim_hours: float                              # 总模拟时长（小时）
    coordinates: dict[str, list[float]]           # 节点名 -> [X, Y]


def load_inp(inp_path: str | Path) -> SwmmInpData:
    """读取并解析 .inp 文件，返回模拟元信息（时长 + 坐标）。"""
    path = Path(inp_path).expanduser().resolve()
    if not path.exists() or path.suffix.lower() != ".inp":
        raise ValueError(f"Invalid INP file: {path}")
    text = _read_text_file(path)
    options = parse_inp_options(text)
    start, end, sim_hours = compute_sim_hours(options)
    coordinates = parse_inp_coordinates(text)
    return SwmmInpData(
        path=path,
        options=options,
        start=start,
        end=end,
        sim_hours=sim_hours,
        coordinates=coordinates,
    )


# ---------------------------------------------------------------------------
# RPT 解析（原有逻辑，统一缩进与文本读取方式）
# ---------------------------------------------------------------------------


def _read_report(report_path: str | Path) -> tuple[Path, str]:
    """读取报告文件内容，并返回规范化路径和文本内容。"""
    path = Path(report_path).expanduser().resolve()
    if not path.exists() or path.suffix.lower() != ".rpt":
        raise FileNotFoundError(f"Invalid report file: {path}")
    return path, _read_text_file(path)


def _extract_flow_unit(text: str) -> str:
    """从 Analysis Options 章节读取报告使用的流量单位。"""

    match = re.search(r"^\s*Flow Units\s+\.+\s*(\S+)\s*$", text, re.MULTILINE)
    if not match:
        raise ValueError("Could not find 'Flow Units' in report.")
    return match.group(1)


def _extract_float_from_section_line(
    text: str,
    header: str,
    label: str,
    *,
    field_name: str,
    value_index: int = -1,
) -> float:
    """在指定章节内定位某一行，并提取该行最后一个浮点数。

    有些 SWMM 报告会把列对齐格式写得很紧，甚至把点号和数值粘在一起。
    这时不要再依赖固定的空格宽度，而是先找到目标行，再从行尾抽取最后一个数值。
    """

    lines = text.splitlines()
    start_index: int | None = None
    for index, raw in enumerate(lines):
        if header in raw:
            start_index = index
            break
    if start_index is None:
        raise ValueError(f"Could not find '{field_name}' in report.")

    data_started = False
    for raw in lines[start_index + 1 :]:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("*"):
            if data_started:
                break
            continue
        if line.startswith(label):
            data_started = True
            numbers = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", line)
            if not numbers:
                raise ValueError(f"Could not find '{field_name}' in report.")
            try:
                return float(numbers[value_index])
            except IndexError as exc:
                raise ValueError(f"Could not find '{field_name}' in report.") from exc

    raise ValueError(f"Could not find '{field_name}' in report.")


def _extract_section_lines(text: str, header: str) -> list[str]:
    """抓取某个章节标题后的有效数据行（跳过说明、横线和空行）。

    返回值是一个字符串列表，每个元素对应一行数据。
    """

    lines = text.splitlines()
    start_index: int | None = None
    for index, raw in enumerate(lines):
        if header in raw:
            start_index = index
            break
    if start_index is None:
        return []

    data_lines: list[str] = []
    data_started = False
    for raw in lines[start_index + 1 :]:
        line = raw.rstrip()
        strip_line = line.strip()

        if data_started and strip_line.startswith("***"):
            break
        if data_started and strip_line.endswith("Summary"):
            break

        if (
            not strip_line
            or strip_line.startswith("*")
            or set(strip_line) == {"-"}
            or "Flooding refers" in strip_line
        ):
            continue

        # 有些表头会分成多行，真正数据行一般以对象 ID 开头。
        if re.match(r"^\s*[A-Za-z][\w.-]*\s+", line):  # [前导空格] 对象ID [空格] 其他数据
            data_started = True
            data_lines.append(line)

    return data_lines


def _parse_outfall_flows(text: str) -> list[OutfallFlow]:
    """解析 Outfall Loading Summary 节，返回 OutfallFlow 列表。"""
    items: list[OutfallFlow] = []
    for line in _extract_section_lines(text, "Outfall Loading Summary"):
        match = re.match(
            r"^\s*(?P<node>\S+)\s+(?P<freq>[-\d.]+)\s+(?P<avg>[-\d.]+)\s+(?P<max>[-\d.]+)\s+(?P<total>[-\d.]+)\s*$",
            line,
        )  # [前导空格] node名字 freq数字 avg数字 max数字 total数字 [末尾空格]
        if not match:
            continue
        items.append(
            OutfallFlow(
                node=match.group("node"),
                flow_frequency=float(match.group("freq")),
                average_flow=float(match.group("avg")),
                maximum_flow=float(match.group("max")),
                total_volume=float(match.group("total")),
            )
        )
    if not items:
        raise ValueError("Could not parse 'Outfall Loading Summary' from report.")
    return items


def _parse_node_flooding(text: str) -> list[NodeFlooding]:
    """解析 Node Flooding Summary 节，返回 NodeFlooding 列表。"""
    items: list[NodeFlooding] = []
    for line in _extract_section_lines(text, "Node Flooding Summary"):
        match = re.match(
            r"^\s*(?P<node>\S+)\s+(?P<hours>[-\d.]+)\s+(?P<rate>[-\d.]+)\s+(?P<day>\d+)\s+(?P<hm>\d{2}:\d{2})\s+(?P<volume>[-\d.]+)\s+(?P<ponded>[-\d.]+)",
            line,
        )  # [前导空格] node名字 hours数字 rate数字 day数字 hm时间 volume数字 ponded数字 [末尾空格]
        if not match:
            continue
        items.append(
            NodeFlooding(
                node=match.group("node"),
                hours_flooded=float(match.group("hours")),
                maximum_rate=float(match.group("rate")),
                time_of_max=f"{match.group('day')} {match.group('hm')}",
                total_flood_volume=float(match.group("volume")),
                maximum_ponded_volume=float(match.group("ponded")),
            )
        )
    return items


def _parse_link_peak_flows(text: str) -> list[LinkPeakFlow]:
    """解析 Link Flow Summary 节，返回 LinkPeakFlow 列表。"""
    items: list[LinkPeakFlow] = []
    for line in _extract_section_lines(text, "Link Flow Summary"):
        match = re.match(
            r"^\s*(?P<link>\S+)\s+(?P<link_type>\S+)\s+(?P<flow>[-\d.]+)\s+(?P<day>\d+)\s+(?P<hm>\d{2}:\d{2})\s+(?P<velocity>[-\d.]+)\s+(?P<full_flow>[-\d.]+)\s+(?P<full_depth>[-\d.]+)",
            line,
        )  # [前导空格] link名字 link_type名字 flow数字 day数字 hm时间 velocity数字 full_flow数字 full_depth数字 [末尾空格]
        if not match:
            continue
        items.append(
            LinkPeakFlow(
                link=match.group("link"),
                link_type=match.group("link_type"),
                maximum_flow=float(match.group("flow")),
                time_of_max=f"{match.group('day')} {match.group('hm')}",
                maximum_velocity=float(match.group("velocity")),
                max_full_flow=float(match.group("full_flow")),
                max_full_depth=float(match.group("full_depth")),
            )
        )
    return items


def _parse_conduit_surcharge(text: str) -> list[ConduitSurcharge]:
    """解析 Conduit Surcharge Summary 节，返回 ConduitSurcharge 列表。"""
    items: list[ConduitSurcharge] = []
    for line in _extract_section_lines(text, "Conduit Surcharge Summary"):
        match = re.match(
            r"^\s*(?P<conduit>\S+)\s+(?P<both>[-\d.]+)\s+(?P<up>[-\d.]+)\s+(?P<down>[-\d.]+)\s+(?P<above>[-\d.]+)\s+(?P<limited>[-\d.]+)",
            line,
        )  # [前导空格] conduit名字 both数字 up数字 down数字 above数字 limited数字 [末尾空格]
        if not match:
            continue
        items.append(
            ConduitSurcharge(
                conduit=match.group("conduit"),
                hours_full_both_ends=float(match.group("both")),
                hours_full_upstream=float(match.group("up")),
                hours_full_downstream=float(match.group("down")),
                hours_above_full_normal_flow=float(match.group("above")),
                hours_capacity_limited=float(match.group("limited")),
            )
        )
    return items


def parse_report_flows(report_path: str | Path) -> SwmmReportSummary:
    """解析 RPT 并返回三类流量信息 + 系统关键质量指标。"""

    path, text = _read_report(report_path)
    flow_unit = _extract_flow_unit(text)

    # 这几个字段的报告格式不够稳定，部分报告会把点号和数值挤在一起。
    # 先定位到目标行，再从该行末尾取最后一个数值，能兼容更多 SWMM 输出格式。
    runoff_continuity_error = _extract_float_from_section_line(
        text,
        "Runoff Quantity Continuity",
        "Continuity Error (%)",
        field_name="Runoff Continuity Error",
    )
    routing_continuity_error = _extract_float_from_section_line(
        text,
        "Flow Routing Continuity",
        "Continuity Error (%)",
        field_name="Flow Routing Continuity Error",
    )
    flooding_loss_volume = _extract_float_from_section_line(
        text,
        "Flow Routing Continuity",
        "Flooding Loss",
        field_name="Flooding Loss",
        value_index=0,
    )
    flooding_loss_volume_secondary = _extract_float_from_section_line(
        text,
        "Flow Routing Continuity",
        "Flooding Loss",
        field_name="Flooding Loss (secondary volume)",
        value_index=1,
    )

    outfall_flows = _parse_outfall_flows(text)
    node_flooding = _parse_node_flooding(text)
    link_peak_flows = _parse_link_peak_flows(text)
    conduit_surcharge = _parse_conduit_surcharge(text)

    return SwmmReportSummary(
        report_path=path,
        flow_unit=flow_unit,
        runoff_continuity_error=runoff_continuity_error,
        routing_continuity_error=routing_continuity_error,
        flooding_loss_volume=flooding_loss_volume,
        flooding_loss_volume_secondary=flooding_loss_volume_secondary,
        outfall_flows=outfall_flows,
        node_flooding=node_flooding,
        link_peak_flows=link_peak_flows,
        conduit_surcharge=conduit_surcharge,
    )


def parse_report(report_path: str | Path) -> SwmmReportSummary:
    """兼容入口：保留原函数名，内部调用新版流量解析函数。"""

    return parse_report_flows(report_path)


# ---------------------------------------------------------------------------
# 速率计算与输出 JSON 构建
# ---------------------------------------------------------------------------

# 单位换算常数：报告里的体积列单位是 10^6 ltr（百万升），1 百万升 = 1000 立方米。
# 程序内部一律先换算成 m3 再相加：
#     volume_m3 = volume_1e6ltr * 1000
#     rate(m3/s) = total_volume_m3 / (sim_hours * 3600)
_HOURS_TO_SECONDS = 3600.0
_LITERS_PER_MILLION = 1000.0
_VOLUME_TO_FLOW_FACTOR = _HOURS_TO_SECONDS / _LITERS_PER_MILLION  # == 3.6（旧口径，保留兼容）
_M3_PER_1E6_LITRE = 1000.0

# 速率保留的小数位数（按任务要求取 6 位，不会过度舍入）；
# 设为 None 可输出 float 原始精度。
_RATE_DECIMALS = 6

# ---------------------------------------------------------------------------
# rate 的两套计算口径（两个 JSON 文件的唯一区别 = 要不要算汇水区地表蓄水）
#   * without_subcatchment_storage —— 节点溢流量 + 出水口排放量（本模块的主口径，
#     输出 rate_<名>.json）。汇水区滞蓄的那部分水量**不在这里**，它由虚拟降雨
#     雨型 chi_<名>.txt 代表，所以点位 + 面雨 = 全部水量，不会重复也不会丢。
#   * with_subcatchment_storage —— 上面两项 + Σ关联汇水区地表蓄水量（历史口径，
#     输出 rate_<名>_with_sub.json）
# ---------------------------------------------------------------------------
RATE_BASIS_WITHOUT_SUB = "without_subcatchment_storage"
RATE_BASIS_WITH_SUB = "with_subcatchment_storage"
RATE_BASIS_CHOICES: tuple[str, ...] = (RATE_BASIS_WITHOUT_SUB, RATE_BASIS_WITH_SUB)

# 上一版用过的口径名，仍然接受（值统一归一化到 RATE_BASIS_WITHOUT_SUB）。
RATE_BASIS_ALIASES: dict[str, str] = {
    "flood_only": RATE_BASIS_WITHOUT_SUB,       # 早期只算 junction 溢流的写法
    "flood_and_outfall": RATE_BASIS_WITHOUT_SUB,
}

# 主口径（rate_<名>.json）里参与 rate 的节点溢流水量：包含 junction 溢流，
# 也包含非 junction 节点（例如 outfall）自身的溢流 —— 两者都是"离开管网"的水。
# 实测本项目的两个案例里，溢流全部发生在 junction（非 junction 溢流量 = 0），
# 所以 "junction 溢流" 与 "全部节点溢流" 数值相同；这里取后者以免别的模型丢水。

RATE_BASIS_NOTES: dict[str, str] = {
    RATE_BASIS_WITHOUT_SUB: (
        "不含汇水区地表蓄水：rate = (该节点累计溢流量 + 该节点累计排放量(m3)) / "
        "(sim_hours * 3600)。汇水区滞蓄的那部分水量由虚拟降雨雨型 "
        "chi_<主干名>.txt 代表，因此「点位 rate × 时间 + 面雨」正好等于全部水量。"),
    RATE_BASIS_WITH_SUB: (
        "含汇水区地表蓄水：rate = (该节点累计溢流量 + 累计排放量 + Σ关联汇水区"
        "地表蓄水量) / (sim_hours * 3600)，即本模块的历史口径。"),
}

# 每个口径参与 rate 的水量构成（写进 meta，便于下游核对）。
RATE_BASIS_COMPONENTS: dict[str, list[str]] = {
    RATE_BASIS_WITHOUT_SUB: ["node_flood_volume_m3", "outfall_outflow_m3"],
    RATE_BASIS_WITH_SUB: [
        "node_flood_volume_m3", "outfall_outflow_m3", "surface_storage_m3"],
}


def check_rate_basis(rate_basis: str) -> str:
    """校验 rate 口径取值，返回规范化后的名称（兼容旧别名）。"""
    normalized = RATE_BASIS_ALIASES.get(rate_basis, rate_basis)
    if normalized not in RATE_BASIS_CHOICES:
        raise ValueError(
            f"未知的 rate_basis: {rate_basis!r}，可选：{list(RATE_BASIS_CHOICES)}"
            f"（兼容别名：{list(RATE_BASIS_ALIASES)}）")
    return normalized


def _round_rate(value: float) -> float:
    """对速率做合理精度舍入；_RATE_DECIMALS 为 None 时保留原精度。"""
    if _RATE_DECIMALS is None:
        return value
    return round(value, _RATE_DECIMALS)


def _rpt_volume_to_m3(volume_1e6ltr: float) -> float:
    """报告体积列（10^6 ltr）-> m3。"""
    return volume_1e6ltr * _M3_PER_1E6_LITRE


def build_outlet_aggregates(
    inp_path: str | Path,
    rpt_path: str | Path,
    summary: SwmmReportSummary,
    inp: SwmmInpData,
    *,
    surface_storage: str = "auto",
    scale_storage_to_reported: bool = True,
    include_real_outfalls: bool = False,
) -> tuple[list[OutletAggregate], dict[str, object], dict[str, SubcatchmentStorage]]:
    """计算逐出水口的水量构成与速率。

    total_volume_m3 = 节点累计溢流量(m3)
                    + 节点累计排放量(m3，仅 Outfall 有)
                    + Σ(该出水口关联的所有汇水区地表蓄水量)(m3)
    rate = total_volume_m3 / (sim_hours * 3600)   # m3/s，与既有时间口径一致

    surface_storage:
      "auto"        -> 自动用质量平衡反推（默认，见模块 docstring）
      "off"         -> 关闭（rate 只含溢流+出流，并在 meta 中告警）
      "mass_balance"-> 同 auto

    include_real_outfalls:
      False（默认）-> rate 表只保留 junction(J*) 与虚拟出水口(sea*/mount*)，
                      真实排放口(out*) 被排除，明细见
                      original.excluded_real_outfalls
      True         -> 把真实排放口也放进 rate 表（旧行为）

    返回 (逐出水口聚合, 取数元数据, 逐汇水区蓄水量)。
    """
    inp_text = _read_text_file(Path(inp_path).expanduser().resolve())
    subcatchments = parse_inp_subcatchments(inp_text)
    outfalls = parse_inp_outfalls(inp_text)
    junctions = parse_inp_junctions(inp_text)
    polygons = parse_inp_polygons(inp_text)
    node_names = set(junctions) | {o.name for o in outfalls}
    junction_set = set(junctions)
    outfall_names = {o.name for o in outfalls}

    # ---- 汇水区 -> 出水口 ----
    outlet_map, outlet_warnings = build_outlet_map(subcatchments, node_names)

    # ---- 汇水区地表蓄水量 ----
    storage_meta: dict[str, object] = {
        "enabled": surface_storage != "off",
        "method": None,
        "raw_total_m3": 0.0,
        "reported_total_m3": None,
        "scale_factor": 1.0,
        "engine_note": "",
        "warnings": list(outlet_warnings),
    }
    storage_by_name: dict[str, SubcatchmentStorage] = {}
    if surface_storage != "off":
        result = compute_surface_storage(
            inp_path, rpt_path, scale_to_reported=scale_storage_to_reported)
        storage_by_name = result.by_name()
        storage_meta.update({
            "method": result.method,
            "raw_total_m3": result.raw_total_m3,
            "reported_total_m3": result.reported_total_m3,
            "scale_factor": result.scale_factor,
            "total_area_m2": result.total_area_m2,
            "unit_choices": result.unit_choices,
            "engine_note": result.engine_note,
            "warnings": list(outlet_warnings) + list(result.warnings),
        })
    else:
        storage_meta["warnings"].append(
            "surface_storage='off'：rate 中未包含汇水区地表蓄水量，"
            "总水量只含节点溢流与排放口出流，会偏低。")

    storage_by_outlet: dict[str, float] = {}
    for outlet, names in outlet_map.items():
        total = 0.0
        for nm in names:
            item = storage_by_name.get(nm)
            if item is None:
                if surface_storage != "off":
                    raise SurfaceStorageError(
                        f"汇水区 {nm} 的地表蓄水量缺失，拒绝填 0。")
                continue
            total += item.storage_m3
        storage_by_outlet[outlet] = total

    # ---- 节点水量（报告体积列 -> m3）----
    flood_by_node = {f.node: _rpt_volume_to_m3(f.total_flood_volume)
                     for f in summary.node_flooding}
    outfall_by_node = {o.node: _rpt_volume_to_m3(o.total_volume)
                       for o in summary.outfall_flows}

    # ---- 虚拟出水口的判定 + rate 表的节点集合 ----
    # 【新口径 · 简化】判据不再是名字前缀，而是：
    #     **只要被汇水区在 [SUBCATCHMENTS] 的 Outlet 列点到名，就视为虚拟出水口**
    #     （不管它是 J* / sea* / mount* / vir* / out* 中的哪一种）。
    #   另外，[OUTFALLS] 里名字以 sea* / mount* / vir* 开头的，也按其命名视为虚拟出水口。
    # 因此 rate 表里保留的就是这些"虚拟出水点"，外加**未被指定但有节点溢流**的节点
    #   （不这样会丢掉那部分溢流水量）。
    # 真正的"实际排放口"（[OUTFALLS] 里，既未被任何汇水区指定、名字也不是
    #   sea*/mount*/vir*）不进入 rate 表；其原始出流仍完整保留在 original.outfall_flows，
    #   逐个明细见 original.excluded_real_outfalls。
    #   如需把全部真实排放口也放进 rate，用 include_real_outfalls=True。
    # 注意：这里同时保留"有序清单"和"集合"两种形式。
    # rate 表的节点顺序必须**可复现**：如果直接遍历 set，Python 的字符串哈希
    # 随机化(PYTHONHASHSEED)会让同一份输入在不同进程里产出不同的节点顺序
    # （实测：同一 .inp/.rpt 两次运行，rate 顺序不同、数值完全相同）。
    # 因此顺序一律取自 [SUBCATCHMENTS] / [OUTFALLS] / .rpt 的自然顺序。
    designated_order = list(outlet_map.keys())               # 按 [SUBCATCHMENTS] 顺序
    virtual_by_name_order = [o.name for o in outfalls if o.is_virtual]   # 按 [OUTFALLS] 顺序
    designated_by_subcatchment = set(designated_order)
    virtual_by_name = set(virtual_by_name_order)
    virtual_names = designated_by_subcatchment | virtual_by_name

    system_rows = [n for n in outfall_by_node if n.strip().lower() == "system"]
    for n in system_rows:
        storage_meta["warnings"].append(
            f"Outfall Loading Summary 的 '{n}' 汇总行是系统总量而非真实节点，"
            "已保留在 original.outfall_flows，但不进入 rate 列表。")

    candidates: OrderedDict[str, None] = OrderedDict()
    for nm in designated_order:                              # 汇水区指定的虚拟出水口
        candidates.setdefault(nm, None)
    for nm in virtual_by_name_order:                         # 按名字认定的虚拟出水口
        candidates.setdefault(nm, None)
    for nm in flood_by_node:                                 # 溢流节点（未被指定的也要收）
        candidates.setdefault(nm, None)

    real_outfalls = {o.name for o in outfalls if not o.is_virtual}
    excluded: list[dict[str, object]] = []
    kept_by_designation: list[dict[str, object]] = []
    if include_real_outfalls:
        for nm in outfall_by_node:
            if nm not in system_rows:
                candidates.setdefault(nm, None)
    else:
        # 实际排放口 = Outfall 类型、且不在虚拟集合里
        for nm in list(outfall_by_node):
            if nm in system_rows or nm in virtual_names:
                continue
            st = storage_by_outlet.get(nm, 0.0)
            fl = flood_by_node.get(nm, 0.0)
            of = outfall_by_node.get(nm, 0.0)
            candidates.pop(nm, None)
            excluded.append({
                "node": nm,
                "reason": ("实际排放口（未被任何汇水区指定为 Outlet，"
                           "名字也不是 sea*/mount*/vir*），不进入 rate 表"),
                "surface_storage_m3": round(st, 6),
                "node_flood_volume_m3": round(fl, 6),
                "outfall_outflow_m3": round(of, 6),
                "total_m3": round(st + fl + of, 6),
                "n_subcatchments": len(outlet_map.get(nm, ())),
                "subcatchments": list(outlet_map.get(nm, ())),
            })
        lost = [x for x in excluded
                if float(x["surface_storage_m3"]) > 1e-9 or float(x["node_flood_volume_m3"]) > 1e-9]
        if lost:
            storage_meta["warnings"].append(
                f"⚠️ 有 {len(lost)} 个实际排放口本身还携带汇水区地表蓄水/节点溢流，"
                f"合计 {sum(float(x['surface_storage_m3']) + float(x['node_flood_volume_m3']) for x in lost):,.3f} m3。"
                "这部分水量**不会出现在 rate 表里**。如果也要送给 LISFLOOD，"
                "请改用 --include-real-outfalls，或把这些汇水区的 Outlet 改到虚拟出水口。"
                "明细见 original.excluded_real_outfalls。")
    # 被汇水区指定、但名字看起来像实际排放口的点（提示用；新口径下它们已是虚拟出水口）
    for nm in sorted(designated_by_subcatchment & real_outfalls):
        kept_by_designation.append({
            "node": nm,
            "reason": "被汇水区指定为 Outlet，按新口径视为虚拟出水口，保留在 rate 表",
            "surface_storage_m3": round(storage_by_outlet.get(nm, 0.0), 6),
            "node_flood_volume_m3": round(flood_by_node.get(nm, 0.0), 6),
            "outfall_outflow_m3": round(outfall_by_node.get(nm, 0.0), 6),
            "n_subcatchments": len(outlet_map.get(nm, ())),
            "subcatchments": list(outlet_map.get(nm, ())),
        })

    aggregates: list[OutletAggregate] = []
    seconds = inp.sim_hours * _HOURS_TO_SECONDS
    for node in candidates:
        subs = tuple(outlet_map.get(node, ()))
        st = storage_by_outlet.get(node, 0.0)
        fl = flood_by_node.get(node, 0.0)
        of = outfall_by_node.get(node, 0.0)
        total = st + fl + of
        cls = "junction" if node in junction_set else (
            "outfall" if node in outfall_names else "other")
        is_virtual = node in virtual_names
        coord = inp.coordinates.get(node)
        src = "coordinates" if coord else "none"
        if coord is None:
            coord, src = _resolve_virtual_outfall_coordinate(
                node, inp.coordinates, list(subs), polygons)
        # 主口径（不含汇水区地表蓄水）= 该节点溢流量 + 该节点排放口排放量。
        # 两者都是"离开管网"的水：溢流从节点漫出，排放量从 sea*/mount* 排走；
        # 留在汇水区地表的水由虚拟降雨雨型代表，不能在这里再算一遍。
        without_sub_volume = fl + of
        nonjunction_flood = 0.0 if node in junction_set else fl
        aggregates.append(
            OutletAggregate(
                node=node, node_class=cls, is_virtual_outfall=is_virtual,
                coordinate=coord, coordinate_source=src, subcatchments=subs,
                surface_storage_m3=st, node_flood_volume_m3=fl,
                outfall_outflow_m3=of, total_volume_m3=total,
                without_sub_volume_m3=without_sub_volume,
                nonjunction_flood_volume_m3=nonjunction_flood,
                rate_with_sub=_round_rate(total / seconds),
                rate_without_sub=_round_rate(without_sub_volume / seconds),
            )
        )

    nodes_without_coord = [a.node for a in aggregates if a.coordinate is None]
    if nodes_without_coord:
        storage_meta["warnings"].append(
            f"{len(nodes_without_coord)} 个出水口既无 [COORDINATES] 也无多边形质心，"
            f"coordinate 输出 null：{nodes_without_coord[:8]}")

    # ---- 重要提醒：开了 ponding 时，“节点溢流量”并不是离开 SWMM 的水量 ----
    total_flood_m3 = sum(a.node_flood_volume_m3 for a in aggregates)
    flood_loss_m3 = summary.flooding_loss_volume * _M3_PER_HECTARE_M
    storage_meta["flooding_retention_check"] = {
        "node_flooding_total_m3": total_flood_m3,
        "flow_routing_flooding_loss_m3": flood_loss_m3,
        "retained_in_swmm_m3": max(0.0, total_flood_m3 - flood_loss_m3),
        "retained_pct": (100.0 * max(0.0, total_flood_m3 - flood_loss_m3) / total_flood_m3
                         if total_flood_m3 else 0.0),
    }
    if total_flood_m3 > 0.0 and flood_loss_m3 < 0.5 * total_flood_m3:
        storage_meta["warnings"].append(
            f"本模型 Flow Routing Continuity 的 Flooding Loss 只有 {flood_loss_m3:,.0f} m3，"
            f"而 Node Flooding Summary 的溢流总量是 {total_flood_m3:,.0f} m3 —— "
            f"说明约 {100.0 * (1 - flood_loss_m3 / total_flood_m3):.1f}% 的溢流水被 "
            "ALLOW_PONDING 积在节点地表、并没有离开 SWMM（它已计入 Final Stored Volume）。"
            "把这份水量送给外部二维模型（LISFLOOD）时，必须同时把 SWMM 设成 "
            "ALLOW_PONDING = NO（或把 junction 的 Aponded 置 0），否则同一份水会被算两遍。")

    n_virtual = sum(1 for a in aggregates if a.is_virtual_outfall)
    n_flood_only = sum(1 for a in aggregates
                       if not a.is_virtual_outfall and a.node_flood_volume_m3 > 0.0)
    excluded_outflow_m3 = sum(float(x["outfall_outflow_m3"]) for x in excluded)
    excluded_storage_m3 = sum(float(x["surface_storage_m3"]) for x in excluded)
    excluded_flood_m3 = sum(float(x["node_flood_volume_m3"]) for x in excluded)
    storage_meta.update({
        "n_outlets": len(aggregates),
        # ---- 新口径：rate 表里的点都是虚拟出水点 ----
        "virtual_outfall_criterion": (
            "只要被汇水区在 [SUBCATCHMENTS] 的 Outlet 列指定，就视为虚拟出水口；"
            "另外 [OUTFALLS] 中名字以 sea*/mount*/vir* 开头的也视为虚拟出水口。"
            "未被指定的实际排放口（如 out1/out2…）不进入 rate 表。"),
        "is_virtual_outfall": True,
        "n_virtual_outfalls_in_rate": n_virtual,
        "n_designated_by_subcatchment": len(designated_by_subcatchment),
        "n_virtual_by_name_prefix": len(virtual_by_name),
        "n_flood_only_nodes_in_rate": n_flood_only,
        "flood_only_nodes_in_rate": sorted(
            a.node for a in aggregates
            if not a.is_virtual_outfall and a.node_flood_volume_m3 > 0.0),
        "n_junctions_in_rate": sum(1 for a in aggregates if a.node_class == "junction"),
        "n_outfall_type_in_rate": sum(1 for a in aggregates if a.node_class == "outfall"),
        "include_real_outfalls": include_real_outfalls,
        "n_subcatchments": len(subcatchments),
        "n_subcatchments_on_virtual_outfalls":
            sum(len(a.subcatchments) for a in aggregates if a.is_virtual_outfall),
        "total_surface_storage_in_rate_m3": sum(a.surface_storage_m3 for a in aggregates),
        "total_node_flood_in_rate_m3": sum(a.node_flood_volume_m3 for a in aggregates),
        "total_outfall_outflow_in_rate_m3": sum(a.outfall_outflow_m3 for a in aggregates),
        "total_volume_in_rate_m3": sum(a.total_volume_m3 for a in aggregates),
        # 主口径（不含汇水区地表蓄水）的总量 = 全部节点溢流 + 全部出水口排放量。
        "total_without_sub_volume_in_rate_m3":
            sum(a.without_sub_volume_m3 for a in aggregates),
        # 其中溢流发生在非 junction 节点（例如 outfall）的部分（信息用，已计入 rate）。
        "nonjunction_flood_volume_m3":
            sum(a.nonjunction_flood_volume_m3 for a in aggregates),
        # 被删除的实际排放口（仅用于核对，不进入 rate）
        "n_excluded_real_outfalls": len(excluded),
        "excluded_real_outfalls_outflow_m3": excluded_outflow_m3,
        "excluded_real_outfalls_storage_m3": excluded_storage_m3,
        "excluded_real_outfalls_flood_m3": excluded_flood_m3,
        "excluded_real_outfalls_total_m3": (excluded_outflow_m3 + excluded_storage_m3
                                            + excluded_flood_m3),
        # 被汇水区指定、名字却像实际排放口的点（新口径下已是虚拟出水口）
        "n_kept_real_outfalls_by_subcatchment": len(kept_by_designation),
        "kept_real_outfalls_by_subcatchment": [x["node"] for x in kept_by_designation],
        "kept_real_outfalls_by_subcatchment_total_m3":
            sum(float(x["surface_storage_m3"]) + float(x["node_flood_volume_m3"])
                + float(x["outfall_outflow_m3"]) for x in kept_by_designation),
        "rate_time_basis": (f"sim_hours={inp.sim_hours} h "
                            f"({inp.options.get('START_DATE')} {inp.options.get('START_TIME')}"
                            f" -> {inp.options.get('END_DATE')} {inp.options.get('END_TIME')})"),
    })
    storage_meta["excluded_real_outfalls"] = excluded
    storage_meta["kept_real_outfalls_by_subcatchment"] = kept_by_designation
    return aggregates, storage_meta, storage_by_name


def _basis_meta(
    storage_meta: dict[str, object],
    aggregates: list[OutletAggregate],
    inp: SwmmInpData,
    rate_basis: str,
) -> dict[str, object]:
    """在共享 meta 之上补一份「本文件用的是哪套 rate 口径」的说明。

    返回浅拷贝（warnings 也复制一份），因此两个口径的 JSON 可以各自带上自己的
    告警而互不影响。
    """
    basis = check_rate_basis(rate_basis)
    meta = dict(storage_meta)
    meta["warnings"] = list(storage_meta.get("warnings", ()))  # type: ignore[arg-type]
    rate_volume = sum(a.rate_volume_m3_for(basis) for a in aggregates)
    meta.update({
        "rate_basis": basis,
        "rate_basis_note": RATE_BASIS_NOTES[basis],
        "rate_basis_components": list(RATE_BASIS_COMPONENTS[basis]),
        "rate_basis_volume_in_rate_m3": rate_volume,
        "rate_basis_total_m3s": sum(a.rate_for(basis) for a in aggregates),
    })
    if basis == RATE_BASIS_WITHOUT_SUB:
        meta["rate_basis_excluded_components"] = ["surface_storage_m3"]
        # 两个口径的水量核对：本口径 + 汇水区地表蓄水 = with_sub 口径（应严格相等）。
        storage_total = sum(a.surface_storage_m3 for a in aggregates)
        with_sub_total = sum(a.total_volume_m3 for a in aggregates)
        meta["rate_basis_water_balance_check"] = {
            "without_sub_m3": rate_volume,
            "surface_storage_m3": storage_total,
            "sum_m3": rate_volume + storage_total,
            "with_sub_m3": with_sub_total,
            "difference_m3": rate_volume + storage_total - with_sub_total,
            "note": ("主口径（点位）+ 汇水区地表蓄水（虚拟降雨）= 含蓄水口径，"
                     "两种交付方案水量等价、不重不漏。"),
        }
        nonjunction = float(meta.get("nonjunction_flood_volume_m3") or 0.0)
        if nonjunction > 1e-9:
            meta["warnings"].append(
                f"注意：有 {nonjunction:,.3f} m3 的溢流发生在**非 junction 节点**"
                "（例如 outfall）；本口径按「全部节点溢流」计入 rate（已包含）。")
    return meta


def _build_original_section(
    summary: SwmmReportSummary,
    inp: SwmmInpData,
    subcatchments: list[SubcatchmentInfo],
    outfalls: list[OutfallInfo],
    aggregates: list[OutletAggregate],
    storage_meta: dict[str, object],
    storage_by_name: dict[str, SubcatchmentStorage],
    *,
    rate_basis: str = RATE_BASIS_WITH_SUB,
) -> dict[str, object]:
    """original 部分：既有解析结果 + INP 元信息 + 坐标 + 新增的汇水区蓄水字段。

    rate_basis 决定 outlet_storage.rate_m3s 与 surface_storage_meta.rate_basis
    用哪套口径（两个 JSON 文件只有这一点不同）。
    """
    basis = check_rate_basis(rate_basis)
    data = summary.to_dict()

    storage_by_outlet = {a.node: a.surface_storage_m3 for a in aggregates}
    sub_storage_by_name = {a.node: set(a.subcatchments) for a in aggregates}

    outfall_flows = []
    for item in data["outfall_flows"]:
        item = dict(item)
        item["surface_storage_m3"] = storage_by_outlet.get(item["node"], 0.0)
        item["subcatchments"] = sorted(sub_storage_by_name.get(item["node"], ()))
        outfall_flows.append(item)

    node_flooding = []
    for item in data["node_flooding"]:
        item = dict(item)
        item["surface_storage_m3"] = storage_by_outlet.get(item["node"], 0.0)
        item["subcatchments"] = sorted(sub_storage_by_name.get(item["node"], ()))
        node_flooding.append(item)

    return {
        "report_path": data["report_path"],
        "inp_path": str(inp.path),
        "flow_unit": data["flow_unit"],
        "rate_basis": basis,
        "start_date": inp.options.get("START_DATE"),
        "start_time": inp.options.get("START_TIME"),
        "end_date": inp.options.get("END_DATE"),
        "end_time": inp.options.get("END_TIME"),
        "sim_hours": inp.sim_hours,
        "runoff_continuity_error": data["runoff_continuity_error"],
        "routing_continuity_error": data["routing_continuity_error"],
        "flooding_loss_volume": data["flooding_loss_volume"],
        "flooding_loss_volume_secondary": data["flooding_loss_volume_secondary"],
        # ---- 原有明细（已为每条追加 surface_storage_m3 / subcatchments）----
        "outfall_flows": outfall_flows,
        "node_flooding": node_flooding,
        "link_peak_flows": data["link_peak_flows"],
        "conduit_surcharge": data["conduit_surcharge"],
        # 额外补充：完整坐标映射，便于下游不读 .inp 也能拿到坐标。
        "coordinates": inp.coordinates,
        # ---- 新增：逐出水口的水量构成（rate 的口径明细，便于核对）----
        "outlet_storage": [
            {
                "node": a.node,
                "node_class": a.node_class,
                "is_virtual_outfall": a.is_virtual_outfall,
                "coordinate": a.coordinate,
                "coordinate_source": a.coordinate_source,
                "n_subcatchments": len(a.subcatchments),
                "subcatchments": list(a.subcatchments),
                "surface_storage_m3": round(a.surface_storage_m3, 6),
                "node_flood_volume_m3": round(a.node_flood_volume_m3, 6),
                "outfall_outflow_m3": round(a.outfall_outflow_m3, 6),
                "total_volume_m3": round(a.total_volume_m3, 6),
                # 主口径的分子 = 溢流量 + 出水口排放量（不含汇水区地表蓄水）
                "without_sub_volume_m3": round(a.without_sub_volume_m3, 6),
                # 两套口径的速率都给出，rate_m3s 是**本文件**用的那一套
                "rate_basis": basis,
                "rate_basis_volume_m3": round(a.rate_volume_m3_for(basis), 6),
                "rate_m3s": a.rate_for(basis),
                "rate_without_sub_m3s": a.rate_without_sub,
                "rate_with_sub_m3s": a.rate_with_sub,
            }
            for a in aggregates
        ],
        # ---- 新增：逐汇水区的地表蓄水量（可追溯，绝不填 0 掩盖）----
        "subcatch_surface_storage": [
            {
                "name": s.name,
                "outlet": s.outlet,
                "area_m2": round(s.area_m2, 6),
                "precip_m3": round(s.precip_m3, 6),
                "runon_m3": round(s.runon_m3, 6),
                "evap_m3": round(s.evap_m3, 6),
                "infil_m3": round(s.infil_m3, 6),
                "runoff_m3": round(s.runoff_m3, 6),
                "surface_storage_raw_m3": round(s.storage_raw_m3, 6),
                "surface_storage_m3": round(s.storage_m3, 6),
                "surface_storage_depth_mm": round(s.storage_depth_mm, 6),
            }
            for s in storage_by_name.values()
        ],
        # ---- 新增：取数方法 / 核对 / 告警 + 本文件的 rate 口径 ----
        "surface_storage_meta": _basis_meta(storage_meta, aggregates, inp, basis),
        # ---- 新增：被删除出 rate 表的真实排放口（保证不丢数据）----
        "excluded_real_outfalls": storage_meta.get("excluded_real_outfalls", []),
        # ---- 新增：因被汇水区指定为 Outlet 而保留的真实排放口 ----
        "kept_real_outfalls_by_subcatchment":
            storage_meta.get("kept_real_outfalls_by_subcatchment", []),
        # ---- 新增：汇水区 -> 出水口 映射 ----
        "subcatchment_outlets": {s.name: s.outlet for s in subcatchments},
        "subcatchments": [asdict(s) for s in subcatchments],
        "outfalls": [asdict(o) for o in outfalls],
    }


@dataclass(frozen=True)
class ReportBundle:
    """一次解析 + 一次复算的全部中间结果。

    两个 rate 口径（不含蓄水 / 含蓄水）共用它，
    因此**汇水区地表蓄水量只复算一次**（那一步要跑一遍 SWMM，约数秒）。
    """

    inp: SwmmInpData
    summary: SwmmReportSummary
    subcatchments: list[SubcatchmentInfo]
    outfalls: list[OutfallInfo]
    aggregates: list[OutletAggregate]
    storage_meta: dict[str, object]
    storage_by_name: dict[str, SubcatchmentStorage]


def prepare_report_bundle(
    inp_path: str | Path,
    rpt_path: str | Path,
    *,
    surface_storage: str = "auto",
    scale_storage_to_reported: bool = True,
    include_real_outfalls: bool = False,
) -> ReportBundle:
    """解析 INP + RPT，并（默认）复算一次以取得逐汇水区地表蓄水量。

    参数含义同 build_output_data()。返回值可直接交给
    build_output_data_from_bundle() 生成任意口径的 dict，不会重复复算。
    """
    inp = load_inp(inp_path)
    summary = parse_report_flows(rpt_path)
    inp_text = _read_text_file(Path(inp_path).expanduser().resolve())
    subcatchments = parse_inp_subcatchments(inp_text)
    outfalls = parse_inp_outfalls(inp_text)

    aggregates, storage_meta, storage_by_name = build_outlet_aggregates(
        inp_path, rpt_path, summary, inp,
        surface_storage=surface_storage,
        scale_storage_to_reported=scale_storage_to_reported,
        include_real_outfalls=include_real_outfalls,
    )
    return ReportBundle(
        inp=inp, summary=summary, subcatchments=subcatchments, outfalls=outfalls,
        aggregates=aggregates, storage_meta=storage_meta,
        storage_by_name=storage_by_name,
    )


def build_output_data_from_bundle(
    bundle: ReportBundle,
    *,
    rate_basis: str = RATE_BASIS_WITH_SUB,
) -> dict[str, object]:
    """按指定 rate 口径，把 ReportBundle 组装成 {rate, original} dict。"""
    basis = check_rate_basis(rate_basis)

    # rate 表：统一为单一列表，不再区分 outflows / nodeflooding
    rate_section = [
        {"node": a.node, "rate": a.rate_for(basis), "coordinate": a.coordinate}
        for a in bundle.aggregates
    ]

    original_section = _build_original_section(
        bundle.summary, bundle.inp, bundle.subcatchments, bundle.outfalls,
        bundle.aggregates, bundle.storage_meta, bundle.storage_by_name,
        rate_basis=basis,
    )

    return {
        "rate": rate_section,
        "original": original_section,
        "rate_basis": basis,
        "rate_basis_note": RATE_BASIS_NOTES[basis],
    }


def build_output_data(
    inp_path: str | Path,
    rpt_path: str | Path,
    *,
    surface_storage: str = "auto",
    scale_storage_to_reported: bool = True,
    include_real_outfalls: bool = False,
    rate_basis: str = RATE_BASIS_WITH_SUB,
) -> dict[str, object]:
    """构建完整输出 dict：{rate: [...], original: {...}}。

    Args:
        inp_path: .inp 输入文件路径（用于解析出水口映射、坐标与复算蓄水量）。
        rpt_path: 与 .inp 对应的 .rpt 结果文件路径。
        surface_storage: "auto"（默认，质量平衡反推）/ "off"。
        scale_storage_to_reported: 是否把反推的蓄水总量缩放到 .rpt 的官方
            Runoff Quantity Continuity -> Final Storage。
        include_real_outfalls: 是否把真实排放口（如 out1/out2…）也放进 rate 表。
            默认 False —— rate 表只保留 junction(J*) 与虚拟出水口(sea*/mount*)，
            被排除的真实排放口明细见 original.excluded_real_outfalls。
        rate_basis: rate 的计算口径。
            * "with_subcatchment_storage"（默认，历史口径）—— 节点溢流量 + 出水口
              排放量 + Σ关联汇水区地表蓄水量；
            * "without_subcatchment_storage" —— 只算前两项（**不含**汇水区地表蓄水，
              那部分水量由虚拟降雨雨型 chi_*.txt 代表）。
            两个口径的节点清单与坐标完全相同，只有 rate 的取值不同。

    Returns:
        可直接 json.dump 的 dict。
    """
    bundle = prepare_report_bundle(
        inp_path, rpt_path,
        surface_storage=surface_storage,
        scale_storage_to_reported=scale_storage_to_reported,
        include_real_outfalls=include_real_outfalls,
    )
    return build_output_data_from_bundle(bundle, rate_basis=rate_basis)


def default_output_path(
    inp_path: str | Path,
    rate_basis: str = RATE_BASIS_WITHOUT_SUB,
) -> Path:
    """某个口径的默认输出路径（RESULTS_DIR 下）。

    * without_subcatchment_storage -> data/results/rate_<主干名>.json
    * with_subcatchment_storage -> data/results/rate_<主干名>_with_sub.json
    """
    stem = Path(inp_path).expanduser().resolve().stem
    if check_rate_basis(rate_basis) == RATE_BASIS_WITHOUT_SUB:
        return RESULTS_DIR / f"rate_{stem}.json"
    return RESULTS_DIR / f"rate_{stem}_with_sub.json"


def with_sub_path_for(main_rate_path: str | Path) -> Path:
    """由主口径（不含蓄水）的路径派生含蓄水口径的路径（主干名后加 _with_sub）。"""
    path = Path(main_rate_path).expanduser()
    return path.with_name(f"{path.stem}_with_sub{path.suffix}")


def _dump_json_file(data: dict[str, object], output: Path) -> Path:
    """把 dict 写成可读 JSON（UTF-8 + indent=4）。"""
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=4)
        handle.write("\n")
    return output


def write_output_file(
    inp_path: str | Path,
    rpt_path: str | Path,
    out_path: str | Path | None = None,
    *,
    surface_storage: str = "auto",
    scale_storage_to_reported: bool = True,
    include_real_outfalls: bool = False,
    rate_basis: str = RATE_BASIS_WITH_SUB,
) -> Path:
    """解析 INP + RPT 并写出**一个** JSON 文件。

    默认输出到 tools/config.py 的 RESULTS_DIR，文件名由 rate_basis 决定
    （见 default_output_path）：without_subcatchment_storage -> rate_<主干名>.json，
    with_subcatchment_storage -> rate_<主干名>_with_sub.json。
    可通过 out_path 覆盖。使用 json.dump(..., indent=4) 保证可读性。

    ⚠️ 只想同时拿到两个口径的文件时请用 write_output_files()：它只复算一次。
    """
    data = build_output_data(
        inp_path, rpt_path,
        surface_storage=surface_storage,
        scale_storage_to_reported=scale_storage_to_reported,
        include_real_outfalls=include_real_outfalls,
        rate_basis=rate_basis,
    )

    if out_path is None:
        output = default_output_path(inp_path, rate_basis)
    else:
        output = Path(out_path).expanduser().resolve()
    return _dump_json_file(data, output)


def write_output_files(
    inp_path: str | Path,
    rpt_path: str | Path,
    out_path: str | Path | None = None,
    *,
    surface_storage: str = "auto",
    scale_storage_to_reported: bool = True,
    include_real_outfalls: bool = False,
) -> tuple[Path, Path]:
    """解析 INP + RPT，**同时写出两个 JSON**（只复算一次地表蓄水量）。

    * `rate_<主干名>.json`           —— 不含汇水区地表蓄水（节点溢流量 + 出水口排放量）
    * `rate_<主干名>_with_sub.json`  —— 再加上 Σ关联汇水区地表蓄水量

    out_path 给出的是**前一个**的路径；后一个由它派生（主干名后加 _with_sub），
    因此 -o check\\out\\rate_demo.json 会同时得到 check\\out\\rate_demo_with_sub.json。

    Returns:
        (不含蓄水口径的 json 路径, 含蓄水口径的 json 路径)
    """
    bundle = prepare_report_bundle(
        inp_path, rpt_path,
        surface_storage=surface_storage,
        scale_storage_to_reported=scale_storage_to_reported,
        include_real_outfalls=include_real_outfalls,
    )

    without_sub_path = (default_output_path(inp_path, RATE_BASIS_WITHOUT_SUB)
                        if out_path is None
                        else Path(out_path).expanduser().resolve())
    with_sub_path = with_sub_path_for(without_sub_path)

    _dump_json_file(
        build_output_data_from_bundle(bundle, rate_basis=RATE_BASIS_WITHOUT_SUB),
        without_sub_path)
    _dump_json_file(
        build_output_data_from_bundle(bundle, rate_basis=RATE_BASIS_WITH_SUB),
        with_sub_path)
    return without_sub_path, with_sub_path


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------


def _resolve_existing_file(value: str | Path, suffix: str, label: str) -> Path:
    """解析并校验输入文件：优先当前目录，其次回退到 data/swmm。"""
    path = Path(value).expanduser()
    if not path.is_absolute() and not path.exists():
        fallback = SWMM_DATA_DIR / path.name
        if fallback.exists():
            path = fallback
    path = path.resolve()
    if not path.exists() or path.suffix.lower() != suffix:
        raise ValueError(f"Invalid {label} file: {path}")
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Parse a SWMM .inp and its .rpt report, then write **two** rate_*.json "
            "summaries into data/results: rate_<stem>.json（不含汇水区地表蓄水："
            "rate = (节点溢流量 + 出水口排放量) / 时长）"
            " 与 rate_<stem>_with_sub.json（再加上 Σ关联汇水区地表蓄水量）。"
            "两个文件的节点清单与坐标完全相同，只有 rate 的取值不同。"
        )
    )
    parser.add_argument("inp", nargs="?", help="Path to the .inp input file")
    parser.add_argument(
        "rpt",
        nargs="?",
        help="Path to the .rpt result file (optional: defaults to the same-stem "
        ".rpt file next to the .inp file)",
    )
    parser.add_argument(
        "-o",
        "--out",
        help="不含蓄水口径那个 JSON 的路径；含蓄水口径由它派生"
             "（主干名后加 _with_sub）。默认 data/results/rate_<inp stem>.json "
             "与 rate_<inp stem>_with_sub.json",
    )
    parser.add_argument(
        "--surface-storage",
        choices=("auto", "mass_balance", "off"),
        default="auto",
        help="汇水区地表蓄水量的取数方式：auto/mass_balance=按 .inp 复算并做质量平衡"
             "反推（默认）；off=不计算（rate 会偏低，仅供调试）。",
    )
    parser.add_argument(
        "--no-scale-storage",
        action="store_true",
        help="不要把反推的蓄水总量缩放到 .rpt 的官方 Final Storage（默认会缩放）。",
    )
    parser.add_argument(
        "--include-real-outfalls",
        action="store_true",
        help="把**全部**真实排放口（out1/out2…）也放进 rate 表。"
             "默认只保留：被汇水区指定为 Outlet 的点（规则1，哪怕名字是 out*）"
             "以及虚拟出水口 sea*/mount*；其余真实排放口被删除。",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="不打印汇总日志。",
    )
    return parser.parse_args(argv)


def _setup_console() -> None:
    """保证中文/Σ 等在"非终端 + gbk"环境下也能打印，且进度实时可见。

    管道或 GUI 里 stdout 不是终端时，Python 默认 (a) 按 8 KB 块缓冲，
    进度要等结束才吐出来；(b) 编码为 gbk，打印 Σ / ⚠ 等字符会抛
    UnicodeEncodeError 直接中断脚本。这里统一改成 UTF-8 + 行缓冲。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace",
                               line_buffering=True)
        except (AttributeError, ValueError, OSError):
            pass


def print_rate_summary(json_path: Path, label: str = "") -> None:
    """打印一个 rate JSON 的关键数字（main.py 也复用这段输出）。"""
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    meta = data["original"]["surface_storage_meta"]
    prefix = f"[{label}] " if label else ""
    print(f"{prefix}JSON: {json_path}")
    print(f"{prefix}rate 口径              : "
          f"{meta.get('rate_basis')} —— {meta.get('rate_basis_components')}")
    print(f"{prefix}rate 条目数            : {len(data['rate'])}")
    print(f"{prefix}  其中 junction 类型   : {meta.get('n_junctions_in_rate')}")
    print(f"{prefix}  其中 outfall 类型    : {meta.get('n_outfall_type_in_rate')}")
    print(f"{prefix}Σ 参与 rate 的水量     : "
          f"{meta.get('rate_basis_volume_in_rate_m3'):,.3f} m3 "
          f"(折合 {meta.get('rate_basis_total_m3s'):,.3f} m3/s)")
    if meta.get("rate_basis") == RATE_BASIS_WITH_SUB:
        print(f"{prefix}  ├ 节点溢流量        : "
              f"{meta.get('total_node_flood_in_rate_m3'):,.3f} m3")
        print(f"{prefix}  ├ 排放口出流量      : "
              f"{meta.get('total_outfall_outflow_in_rate_m3'):,.3f} m3")
        print(f"{prefix}  └ 汇水区地表蓄水量  : "
              f"{meta.get('total_surface_storage_in_rate_m3'):,.3f} m3 "
              f"(反推 {meta.get('raw_total_m3'):,.3f} m3, "
              f"缩放系数 {meta.get('scale_factor'):.6f})")
    else:
        print(f"{prefix}  ├ 节点溢流量        : "
              f"{meta.get('total_node_flood_in_rate_m3'):,.3f} m3")
        print(f"{prefix}  └ 排放口出流量      : "
              f"{meta.get('total_outfall_outflow_in_rate_m3'):,.3f} m3")
        balance = meta.get("rate_basis_water_balance_check") or {}
        if balance:
            print(f"{prefix}  （+ 汇水区地表蓄水量 "
                  f"{balance.get('surface_storage_m3'):,.3f} m3 = 含蓄水口径 "
                  f"{balance.get('with_sub_m3'):,.3f} m3，由虚拟降雨 chi_*.txt 代表）")
    print(f"{prefix}时间口径               : {meta.get('rate_time_basis')}")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python tools/swmm_rpt.py <inp> [<rpt>] [--out <json>]

    一次写出两个 JSON：rate_<主干名>.json（不含汇水区地表蓄水）与
    rate_<主干名>_with_sub.json（加上汇水区地表蓄水）。--out 给的是前者的路径。
    """
    _setup_console()
    args = parse_args(argv)
    if not args.inp:
        print("error: an .inp path is required.", file=sys.stderr)
        return 2

    try:
        inp_path = _resolve_existing_file(args.inp, ".inp", "INP")
        if args.rpt:
            rpt_path = _resolve_existing_file(args.rpt, ".rpt", "RPT")
        else:
            # 未给 rpt 时，自动采用与 inp 同目录同主干的 .rpt。
            rpt_path = inp_path.with_suffix(".rpt")
            if not rpt_path.exists():
                raise ValueError(
                    f"Cannot find result file automatically: {rpt_path}\n"
                    "Pass the .rpt path explicitly."
                )
        without_sub_path, with_sub_path = write_output_files(
            inp_path, rpt_path, out_path=args.out,
            surface_storage=args.surface_storage,
            scale_storage_to_reported=not args.no_scale_storage,
            include_real_outfalls=args.include_real_outfalls,
        )
        if not args.quiet:
            print(f"INP : {inp_path}")
            print(f"RPT : {rpt_path}")
            print_rate_summary(without_sub_path, label="不含蓄水：溢流+出水口排放")
            print()
            print_rate_summary(with_sub_path, label="含蓄水：+汇水区地表蓄水")
    except (ValueError, FileNotFoundError, SurfaceStorageError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
