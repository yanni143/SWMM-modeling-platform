from __future__ import annotations

"""这个文件是项目当前阶段的“总入口脚本”。

1. swmm_runner: 负责运行 SWMM，得到 rpt/out
2. swmm_rpt   : 负责解析 rpt（+ inp），得到结构化结果 rate_*.json

用法
----
    # A. 跑 SWMM 再解析（会就地生成/覆盖 <inp同名>.rpt / .out）
    python main.py LC_MANUAL_23.inp              # 已存在 rpt/out 时报错，不覆盖
    python main.py --force LC_MANUAL_23.inp      # 覆盖 rpt/out 后重新解析

    # B. 只解析已有报告，不重跑 SWMM（推荐日常使用，不会动原始文件）
    python main.py --report LC_MANUAL_23.rpt

    # C. 指定 JSON 输出位置与地表蓄水口径
    python main.py --report LC_MANUAL_23.rpt -o check\\out\\rate_demo.json
    python main.py --report LC_MANUAL_23.rpt --surface-storage off

输出的 JSON 结构（rate 为合并后的单一列表）：
    {
      "rate":     [ {"node": ..., "rate": ..., "coordinate": ...}, ... ],
      "original": { ...解析明细 + 汇水区地表蓄水量 + 核对信息... }
    }
    rate 的每个元素对应一个出水口节点，总水量 =
        节点累计溢流量 + 排放口累计排放量 + Σ(关联汇水区地表蓄水量)
    详见 tools/swmm_rpt.py 的模块文档与 check/out/RATE_JSON_GUIDE.md。
"""

import argparse
import json
import sys
from pathlib import Path

from tools.config import RESULTS_DIR, SWMM_DATA_DIR
from tools.swmm_rpt import parse_report, write_output_file
from tools.swmm_runner import run_simulation


def resolve_report_path(report: str | Path) -> Path:
	# 允许直接传文件名；若根目录下不存在，则自动到 data/swmm 查找。
	report_path = Path(report).expanduser()
	if not report_path.is_absolute() and not report_path.exists():
		report_path = SWMM_DATA_DIR / report_path
	return report_path.resolve()


def parse_args() -> argparse.Namespace:
	# 这里定义主入口支持的命令行参数。
	# 支持三种使用方式：
	# 1. 传入 inp，先运行 SWMM，再解析新生成的 rpt
	# 2. 直接传入 --report，只解析已有 rpt，不重新运行模型
	# 3. 用 -o 指定 JSON 输出路径
	parser = argparse.ArgumentParser(
		description="run SWMM and parse the generated report.",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog=__doc__,
	)
	parser.add_argument(
		"target",
		nargs="?",
		help="Pass a .inp path to run SWMM",
	)
	parser.add_argument("--report", help="Parse an existing .rpt file without running SWMM")
	parser.add_argument("--swmm-exe", help="Optional path to runswmm executable")
	parser.add_argument("--rpt-name", help="Custom report filename when running SWMM")
	parser.add_argument("--out-name", help="Custom output filename when running SWMM")
	parser.add_argument("--force", action="store_true", help="Overwrite existing report/output files")
	parser.add_argument("-o", "--out", help="rate JSON 输出路径（默认 data/results/rate_<主干名>.json）")
	parser.add_argument(
		"--surface-storage",
		choices=("auto", "mass_balance", "off"),
		default="auto",
		help="汇水区地表蓄水量的取数方式：auto/mass_balance=复算并质量平衡反推（默认）；off=不算",
	)
	parser.add_argument(
		"--no-scale-storage",
		action="store_true",
		help="不要把反推的蓄水总量缩放到 .rpt 的官方 Final Storage（默认会缩放）",
	)
	parser.add_argument(
		"--include-real-outfalls",
		action="store_true",
		help="把全部真实排放口（out1/out2…）也放进 rate 表。"
		     "默认只保留被汇水区指定为 Outlet 的点 + 虚拟出水口 sea*/mount*",
	)
	parser.add_argument("-q", "--quiet", action="store_true", help="只打印 JSON 路径")
	return parser.parse_args()


def _print_summary(json_path: Path, inp_path: Path, report_path: Path) -> None:
	"""打印与 tools/swmm_rpt.py 命令行一致的汇总信息。"""
	data = json.loads(Path(json_path).read_text(encoding="utf-8"))
	meta = data["original"]["surface_storage_meta"]
	print(f"INP : {inp_path}")
	print(f"RPT : {report_path}")
	print(f"JSON: {json_path}")
	print(f"rate 条目数            : {len(data['rate'])}")
	print(f"  其中 junction 类型    : {meta.get('n_junctions_in_rate')}")
	print(f"  其中 outfall 类型     : {meta.get('n_outfall_type_in_rate')}")
	print(f"  按 sea*/mount*/vir* 命名: {meta.get('n_virtual_by_name_prefix')}")
	print(f"Σ 汇水区地表蓄水量     : {meta.get('total_surface_storage_in_rate_m3'):,.3f} m3 "
	      f"(反推 {meta.get('raw_total_m3'):,.3f} m3, 缩放系数 {meta.get('scale_factor'):.6f})")
	print(f"Σ 节点溢流量           : {meta.get('total_node_flood_in_rate_m3'):,.3f} m3")
	print(f"Σ 排放口出流量         : {meta.get('total_outfall_outflow_in_rate_m3'):,.3f} m3")
	print(f"Σ 总水量               : {meta.get('total_volume_in_rate_m3'):,.3f} m3")
	print(f"时间口径               : {meta.get('rate_time_basis')}")


def _setup_console() -> None:
	"""让中文/Σ 在"非终端 + gbk"环境下也能打印，且进度实时可见。

	管道或 GUI 里 stdout 不是终端时，Python 默认按 8 KB 块缓冲（输出要等
	结束才出现），且编码为 gbk；打印 Σ 之类字符会抛 UnicodeEncodeError。
	这里统一改成 UTF-8 + 行缓冲。
	"""
	for stream in (sys.stdout, sys.stderr):
		try:
			stream.reconfigure(encoding="utf-8", errors="replace",
			                   line_buffering=True)
		except (AttributeError, ValueError, OSError):
			pass


def main() -> int:
    # 1. 解析命令行参数
    # 2. 按 report 模式或 run+parse 模式处理
    # 3. 用 write_output_file 生成 rate_<inp主干名>.json（rate + original 两部分）
    _setup_console()
    args = parse_args()

    try:
        if args.report:
            # 纯解析模式：新 JSON 需要 .inp（sim_hours、坐标、出水口映射都来自 INP），
            # 因此用 rpt 的同名主干去找对应的 .inp。
            report_path = resolve_report_path(args.report)
            inp_path = report_path.with_suffix(".inp")
            if not inp_path.exists():
                raise ValueError(
                    f"Cannot find matching INP for report: {inp_path}\n"
                    "The new rate JSON needs the .inp (sim_hours + coordinates)."
                )
        else:
            if not args.target:
                print("Either an INP path or --report must be provided.", file=sys.stderr)
                return 2
            # 提醒：运行模式会就地写入 <inp同名>.rpt / .out。
            if args.force and not args.quiet:
                target = Path(args.target).expanduser()
                if not target.is_absolute() and not target.exists():
                    target = SWMM_DATA_DIR / target
                target = target.resolve()
                print(f"[提示] --force 会覆盖 {target.with_suffix('.rpt').name} 与 "
                      f"{target.with_suffix('.out').name}（即原始报告文件）。\n"
                      "        若只想解析已有报告，请改用："
                      f"python main.py --report {target.with_suffix('.rpt').name}",
                      file=sys.stderr)
            try:
                # 运行模式：先跑 SWMM，再解析新生成的 rpt。
                result = run_simulation(
                    args.target,
                    swmm_exe=args.swmm_exe,
                    rpt_name=args.rpt_name,
                    out_name=args.out_name,
                    force=args.force,
                )
            except (FileNotFoundError, FileExistsError, ValueError) as exc:
                print(str(exc), file=sys.stderr)
                return 2
            if not result.succeeded:
                print(f"SWMM run failed with exit code {result.exit_code}.", file=sys.stderr)
                return result.exit_code
            inp_path = result.inp_path
            report_path = result.rpt_path

        # 统一出口：解析 INP + RPT，写出 rate_*.json。
        json_path = write_output_file(
            inp_path, report_path, out_path=args.out,
            surface_storage=args.surface_storage,
            scale_storage_to_reported=not args.no_scale_storage,
            include_real_outfalls=args.include_real_outfalls,
        )

    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Failed to write JSON file: {exc}", file=sys.stderr)
        return 2

    if args.quiet:
        print(f"JSON saved: {json_path}")
    else:
        _print_summary(Path(json_path), Path(inp_path), Path(report_path))
        print(f"\nJSON saved: {json_path}")
    return 0


if __name__ == "__main__":
	raise SystemExit(main())
