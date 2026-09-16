from __future__ import annotations

"""这个文件是项目当前阶段的“总入口脚本”。

1. swmm_runner: 负责运行 SWMM，得到 rpt/out
2. swmm_rpt   : 负责解析 rpt（+ inp），得到结构化结果 rate_*.json
3. get_chi    : 负责生成虚拟降雨雨型 chi_*.txt

用法
----
    # 区域（--LC / --JJ）是**必填**的：老城与金江分开跑，虚拟降雨要按各自的
    # 二维计算域面积缩放水深，所以必须显式选一个，否则直接报错退出（什么都不输出）。
    #   --LC  老城，二维域 150,174,375 m2（缩放系数 0.7875519…）
    #   --JJ  金江，二维域  63,401,875 m2（缩放系数 0.5407029…）

    # A. 跑 SWMM 再解析（会就地生成/覆盖 <inp同名>.rpt / .out）
    python main.py LC_MANUAL_23.inp --LC         # 已存在 rpt/out 时报错，不覆盖
    python main.py --force LC_MANUAL_23.inp --LC # 覆盖 rpt/out 后重新解析

    # B. 只解析已有报告，不重跑 SWMM（推荐日常使用，不会动原始文件）
    #    默认只出「溢流 + 虚拟降雨」两份，且不复算汇水区地表蓄水量（快）
    python main.py --report LC_MANUAL_23.rpt --LC
    python main.py --report JJ_MANUAL_7.rpt  --JJ

    # C. 需要别的交付物集合时用 --only（见下）
    python main.py --report LC_MANUAL_23.rpt --LC --only all     # 全部（= 旧行为）
    python main.py --report LC_MANUAL_23.rpt --LC --only storage # 只要含蓄水那份
    python main.py --report LC_MANUAL_23.rpt --LC --only overflow# 只要点位表
    python main.py --report LC_MANUAL_23.rpt --LC --only chi     # 只要虚拟降雨
    python main.py --report LC_MANUAL_23.rpt --LC -o check\\out\\rate_demo.json
    python main.py --report LC_MANUAL_23.rpt --LC --surface-storage off
    python main.py --report LC_MANUAL_23.rpt --LC --no-chi # 不生成虚拟降雨雨型

--only 的五个取值（默认 overflow_chi）
----
    all          -> rate_<主干名>.json + rate_<主干名>_with_sub.json + chi_<主干名>.txt
    overflow_chi -> rate_<主干名>.json + chi_<主干名>.txt        （默认，= 方案③）
    overflow     -> rate_<主干名>.json                            （= 方案②）
    chi          -> chi_<主干名>.txt                              （= 方案①）
    storage      -> rate_<主干名>_with_sub.json                   （= 方案④）
    只有 all / storage 需要复算 SWMM 取蓄水量；其余取值会跳过那次复算。

输出（都在 data/results 下，除 -o 指定的除外）
----
1. rate_<主干名>.json          —— rate 表**只算离开管网的水**（不含汇水区地表蓄水）：
      rate = (该节点累计溢流量 + 该节点排放口排放量) / (sim_hours * 3600)
      溢流 = Node Flooding Summary（节点漫出的水）；
      排放量 = Outfall Loading Summary（sea*/mount* 排走的水，例如 sea41）。
      留在汇水区地表的 Final Storage **不在这里算** —— 它由下面的虚拟降雨代表。
2. rate_<主干名>_with_sub.json —— rate 表再加上汇水区地表蓄水：
      rate = (节点累计溢流量 + 排放口累计排放量 + Σ关联汇水区地表蓄水量)
             / (sim_hours * 3600)
   两个文件的节点清单与坐标完全相同，只有 rate 的取值不同，且水量互补：
   ① + ② = 上面那份（Σrate×时长 加 虚拟降雨面雨量 = 含蓄水口径总量），不重不漏。
3. chi_<主干名>.txt            —— 虚拟降雨雨型（芝加哥雨型，[TIMESERIES] 文本）：
      雨量 = .rpt 的 Runoff Quantity Continuity -> Final Storage（mm 列）
             × (SWMM 汇水面积 ÷ 二维域面积)     ← --LC / --JJ 决定这个系数
      历时 = 模拟时间（.inp 的 [OPTIONS] 起止时间之差）
      时序名沿用 get_chi 的 TS<历时>H<雨量>_CHI，例如 TS1H25_CHI。

输出的 JSON 结构（rate 为合并后的单一列表）：
    {
      "rate":     [ {"node": ..., "rate": ..., "coordinate": ...}, ... ],
      "original": { ...解析明细 + 汇水区地表蓄水量 + 核对信息... }
    }
    详见 tools/swmm_rpt.py 的模块文档与 check/out/RATE_JSON_GUIDE.md。
"""

import argparse
import re
import sys
from pathlib import Path

from tools.config import CHI_DOMAINS, RESULTS_DIR, SWMM_DATA_DIR
from tools.get_chi import DEFAULT_DATE as CHI_DEFAULT_DATE
from tools.get_chi import write_chicago_file
from tools.swmm_rpt import (DELIVERABLE_CHOICES, DELIVERABLE_DEFAULT,
                            load_inp, print_rate_summary,
                            read_runoff_final_storage, write_chi,
                            write_output_files, write_rate, write_with_sub)
from tools.swmm_runner import run_simulation

# .inp 里 START_DATE 的形状（MM/DD/YYYY，SWMM 的写法）
_SWMM_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

# 没给 --LC / --JJ 时的报错话术（两个区域是分开跑的，必须显式选一个）。
_NO_DOMAIN_MSG = """错误：必须指定模拟区域。
  本项目的老城（LC）与金江（JJ）是分开跑的，虚拟降雨要按各自的二维计算域
  面积缩放水深，所以请显式二选一：

      python main.py --report LC_MANUAL_23.rpt --LC     # 老城
      python main.py --report JJ_MANUAL_7.rpt  --JJ     # 金江

  （--LC 与 --JJ 互斥，不能同时给；本次没有解析任何文件、也没有写出任何文件。）"""


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
	parser.add_argument("-o", "--out",
	                    help="不含汇水区蓄水那份 JSON 的路径；含蓄水那份由它派生"
	                         "（主干名后加 _with_sub）。默认 data/results/"
	                         "rate_<主干名>.json 与 rate_<主干名>_with_sub.json")
	parser.add_argument(
		"--only",
		choices=DELIVERABLE_CHOICES,
		default=DELIVERABLE_DEFAULT,
		help=f"生成哪些交付物（默认 {DELIVERABLE_DEFAULT}）："
		     "overflow_chi=不含蓄水点位表+虚拟降雨（默认）; overflow=只要点位表; "
		     "chi=只要虚拟降雨; storage=只要含蓄水点位表; all=全都出（旧行为）。"
		     "只有 all/storage 会复算 SWMM 取汇水区地表蓄水量。",
	)
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
	parser.add_argument(
		"--no-chi",
		action="store_true",
		help="不生成虚拟降雨雨型 chi_<主干名>.txt"
		     "（默认会用 .rpt 的 Runoff Final Storage + 模拟时长生成）",
	)
	# 虚拟降雨要撒到哪个二维计算域上（二选一，必须给）。
	# 不给的话 main() 会在解析任何文件之前直接报错退出（什么都不输出）。
	domain_group = parser.add_mutually_exclusive_group()
	domain_group.add_argument(
		"--LC", action="store_true",
		help="老城：虚拟降雨雨深按老城二维域面积 150,174,375 m2 缩放后再生成",
	)
	domain_group.add_argument(
		"--JJ", action="store_true",
		help="金江：虚拟降雨雨深按金江二维域面积 63,401,875 m2 缩放后再生成",
	)
	parser.add_argument("-q", "--quiet", action="store_true", help="只打印输出文件路径")
	return parser.parse_args()


def selected_domain(args: argparse.Namespace) -> str | None:
	"""把 --LC / --JJ 翻成 CHI_DOMAINS 的 key；两个都没给返回 None。"""
	if args.LC:
		return "LC"
	if args.JJ:
		return "JJ"
	return None


def _chi_scale_factor(domain: str) -> float:
	"""虚拟降雨的水深缩放系数 = SWMM 汇水面积 ÷ 二维域面积。

	见 tools/config.py 里 CHI_DOMAINS 的注释：水量守恒要求“乘了面积就得除回来”，
	所以水深要按面积比缩放。
	"""
	cfg = CHI_DOMAINS[domain]
	sub_area = float(cfg["subcatch_area_m2"])
	domain_area = float(cfg["domain_area_m2"])
	if not sub_area or not domain_area:
		raise ValueError(f"{cfg['label']} 的汇水面积或二维域面积没填全，无法缩放")
	return sub_area / domain_area


def build_virtual_rainfall(
	inp_path: Path,
	report_path: Path,
	domain: str,
) -> tuple[Path | None, str]:
	"""生成虚拟降雨雨型 chi_<主干名>.txt，返回 (写出的路径或 None, 说明文字)。

	口径（方案.md 的“溢流+虚拟降雨”）：
	  * 雨量 = .rpt 的 Runoff Quantity Continuity -> Final Storage 的 **mm** 列
	    （即汇水区在模拟结束时仍滞留在地表的水量，按汇水面积折算成雨深）
	  * 历时 = 模拟时间（.inp 的 [OPTIONS] 起止时间之差，sim_hours）
	  * 文件 = data/results/chi_<inp主干名>.txt，由 tools/get_chi.py 生成
	    （芝加哥雨型，r=0.4、5 min 步长，参数不动）

	二维域缩放（domain = "LC" / "JJ"，即命令行 --LC / --JJ）：
	  .rpt 的 mm 是**一维 SWMM 汇水面积**上的水深。二维模型的降雨要撒在更大的
	  二维计算域上，所以必须“水量不变、水深按面积比缩放”：

	      水量 = SWMM 汇水面积 × .rpt 水深        （不变量，缩放前后一样）
	      水深 = 水量 ÷ 二维域面积                （喂给 get_chi 的实际雨深）
	      缩放系数 = SWMM 汇水面积 ÷ 二维域面积

	  面积与系数见 tools/config.py 的 CHI_DOMAINS（老城 0.7875519…、金江 0.5407029…）。

	注意：这里只生成雨型文件，**不会**去改任何 .inp。
	取不到数或写文件失败时不抛异常，返回 (None, 原因)，以免影响已写好的 rate JSON。
	"""
	cfg = CHI_DOMAINS[domain]
	label = str(cfg["label"])

	report_path = Path(report_path)
	ha_m, mm = read_runoff_final_storage(report_path)
	if mm is None:
		reason = (f"{report_path.name} 的 Runoff Quantity Continuity 里找不到 Final Storage")
		print(f"[warn] {reason}，已跳过虚拟降雨雨型的生成。", file=sys.stderr)
		return None, reason
	if mm <= 0:
		reason = f"Final Storage = {mm} mm（<=0），没有可转化的虚拟降雨"
		print(f"[warn] {reason}，已跳过生成。", file=sys.stderr)
		return None, reason

	inp = load_inp(inp_path)
	date_str = inp.options.get("START_DATE") or CHI_DEFAULT_DATE
	if not _SWMM_DATE_RE.match(date_str):
		date_str = CHI_DEFAULT_DATE

	# 缩放系数 = SWMM 汇水面积 ÷ 二维域面积（即 183 行那个乘数）。
	#   老城: 118,270,207.3 / 150,174,375.0 = 0.7875519... => 25.917 mm × 系数 = 20.4110 mm
	#   金江:  34,281,610.5 /  63,401,875.0 = 0.5407029... => 29.959 mm × 系数 = 16.1992 mm
	factor = _chi_scale_factor(domain)
	scaled_mm = factor * mm

	# 输出文件名规则：chi_<输入文件名>.txt，不带区域后缀。
	# 老城与金江的输入文件主干名本来就不同，两份不会互相覆盖。
	out_path = RESULTS_DIR / f"chi_{Path(inp_path).stem}.txt"

	try:
		written = write_chicago_file(
			inp.sim_hours, scaled_mm, out_path=out_path, date_str=date_str, quiet=True)
	except (OSError, ValueError) as exc:
		reason = f"生成虚拟降雨雨型失败：{exc}"
		print(f"[warn] {reason}（rate JSON 已正常写出）。", file=sys.stderr)
		return None, reason

	sub_area = float(cfg["subcatch_area_m2"])
	domain_area = float(cfg["domain_area_m2"])
	note = (f"{label}：雨量 {scaled_mm:.4f} mm = {ha_m:,.3f} hectare-m x "
	        f"汇水面积 {sub_area:,.0f} m2 ÷ 二维域 {domain_area:,.0f} m2"
	        f"（系数 {factor:.6f}，.rpt 原水深 {mm:.3f} mm），"
	        f"历时 {inp.sim_hours:g} h，日期 {date_str}")
	return written, note


def _print_summary(
	rate_paths: list[Path],
	inp_path: Path,
	report_path: Path,
	chi_path: Path | None,
	chi_note: str,
	storage_computed: bool,
	deliverable: str,
) -> None:
	"""打印与 tools/swmm_rpt.py 命令行一致的汇总信息（本次写出的那些文件）。"""
	print(f"INP : {inp_path}")
	print(f"RPT : {report_path}")
	print(f"交付物集合（--only）: {deliverable}")
	for path in rate_paths:
		label = ("含蓄水：+汇水区地表蓄水" if "_with_sub" in Path(path).stem
		         else "不含蓄水：溢流+出水口排放")
		print_rate_summary(path, label=label)
		print()
	if chi_path is not None:
		print(f"CHI : {chi_path}   # 虚拟降雨雨型：{chi_note}")
	else:
		print(f"CHI : 未生成（{chi_note}）")
	if not write_with_sub(deliverable):
		print("提示：本次没有生成 rate_<主干名>_with_sub.json（含蓄水口径）；"
		      "需要时加 --only all 或 --only storage。")
	if not storage_computed and write_rate(deliverable):
		print("提示：本次按 overflow 口径取数，**没有复算** SWMM 引擎，"
		      "不含蓄水口径未做缩放（scale_factor=1.0）。")


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
    # 3. write_output_files 按 --only 写出 rate JSON
    # 4. get_chi 生成虚拟降雨雨型 chi_<主干名>.txt
    _setup_console()
    args = parse_args()

    # 0. 先定区域：--LC / --JJ 必须给一个，否则直接报错退出，
    #    不解析任何文件、不输出任何东西。
    domain = selected_domain(args)
    if domain is None:
        print(_NO_DOMAIN_MSG, file=sys.stderr)
        return 2

    chi_path: Path | None = None
    rate_paths: list[Path] = []
    storage_computed = False

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

        # 统一出口：按 --only 指定的交付物集合写 rate JSON
        #   rate_<主干名>.json          —— 溢流量 + 出水口排放量（不含汇水区地表蓄水）
        #   rate_<主干名>_with_sub.json —— 再加上 Σ关联汇水区地表蓄水量
        # 只有 all / storage 需要复算 SWMM 取蓄水量；其余默认跳过那次复算。
        rate_paths, storage_computed = write_output_files(
            inp_path, report_path, out_path=args.out,
            surface_storage=args.surface_storage,
            scale_storage_to_reported=not args.no_scale_storage,
            include_real_outfalls=args.include_real_outfalls,
            only=args.only,
        )

        # 需要时用 Runoff Final Storage 作雨量、模拟时长作历时，
        # 生成虚拟降雨雨型 data/results/chi_<主干名>.txt
        # （--LC / --JJ 决定雨深按哪个二维域面积缩放）。
        chi_note = "已用 --no-chi 关闭"
        if write_chi(args.only) and not args.no_chi:
            chi_path, chi_note = build_virtual_rainfall(
                Path(inp_path), Path(report_path), domain)
        elif not write_chi(args.only):
            chi_note = f"该交付物集合（--only {args.only}）不含虚拟降雨"

    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Failed to write output files: {exc}", file=sys.stderr)
        return 2

    if args.quiet:
        for path in rate_paths:
            print(f"JSON saved: {path}")
        if chi_path is not None:
            print(f"CHI  saved: {chi_path}")
    else:
        _print_summary(rate_paths, Path(inp_path), Path(report_path),
                       chi_path, chi_note, storage_computed, args.only)
        for path in rate_paths:
            print(f"\nJSON saved: {path}")
        if chi_path is not None:
            print(f"CHI  saved: {chi_path}")
    return 0


if __name__ == "__main__":
	raise SystemExit(main())
