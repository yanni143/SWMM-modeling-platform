"""
解析runswmm.exe位置（用户传入、环境变量SWMM_RUNSWMM、脚本所在目录下的 bin）
输出对应的SwmmRunResult对象，包含inp、rpt、out路径，以及运行结果（exit_code、stdout、stderr）
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tools.config import RUNSWMM_EXE, SWMM_DATA_DIR


@dataclass(frozen=True)
class SwmmRunResult:
	"""这个数据类用于统一承载一次 SWMM 运行的结果。"""
	# frozen=True 表示实例创建后不可修改，适合作为只读结果对象。
	
	inp_path: Path					# 本次运行使用的输入文件。
	
	rpt_path: Path					# 本次运行生成的报告文件。
	
	out_path: Path					# 本次运行生成的二进制结果文件。
	
	exit_code: int					# SWMM 进程退出码，0 一般表示成功。
	
	stdout: str						# SWMM 标准输出，便于调试或记录日志。
	
	stderr: str						# SWMM 标准错误输出，失败时通常会有提示。

	@property
	def succeeded(self) -> bool:
		# 给调用方一个更直观的成功判断，避免到处写 exit_code == 0。
		return self.exit_code == 0


def resolve_runswmm(user_value: str | None) -> Path:
	"""解析runswmm.exe的位置
	
	解析成功则返回一个Path对象，解析失败则抛出FileNotFoundError。
	"""
	# candidates 按优先级收集可能的 runswmm.exe 路径。
	# 当前优先级是：
	# 1. 用户显式传入的路径
	# 2. 当前脚本目录 bin 下的 runswmm.exe
	# 3. PATH 环境变量中能找到的 runswmm
	candidates: list[Path] = []

	if user_value:
		# 如果用户明确指定了可执行文件位置，就优先使用它。
		# expanduser() 允许用户写类似 ~/tool/runswmm.exe 的路径。
		candidates.append(Path(user_value).expanduser())

	# 目录调整后，优先检查仓库根目录下的 bin 目录。
	candidates.append(RUNSWMM_EXE)

	# shutil.which 会到 PATH 中查找名为 runswmm 的可执行程序。
	which_result = shutil.which("runswmm")
	if which_result:
		candidates.append(Path(which_result))

	# 依次检查候选项，找到第一个真实存在的文件就返回。
	for path in candidates:
		if path.exists() and path.is_file():
			return path.resolve()

	# 如果一个都找不到，则把检查过的路径全部报出来，方便定位问题。
	checked = "\n".join(f"  - {p}" for p in candidates)
	raise FileNotFoundError(
		"Cannot find runswmm executable. Checked:\n"
		f"{checked}\n"
		"Use --swmm-exe to set the exact path."
	)


def build_output_paths(inp_path: Path, rpt_name: str | None, out_name: str | None) -> tuple[Path, Path]:
	"""创建输出文件路径，默认与 inp 同目录同名。

	返回值是一个包含 rpt_path 和 out_path 的元组。
	"""
	# 约定 rpt/out 默认与 inp 放在同一目录，并使用 inp 同名主干。
	folder = inp_path.parent
	stem = inp_path.stem
	rpt_path = folder / (rpt_name if rpt_name else f"{stem}.rpt")
	out_path = folder / (out_name if out_name else f"{stem}.out")
	return rpt_path, out_path


def validate_inp_path(inp: str | Path) -> Path:
	"""对输入 INP 路径进行规范化处理与有效性校验
	
	返回值是一个绝对路径的 Path 对象。
	如果路径无效，则抛出 ValueError。"""

	# 统一把输入转成绝对路径，后续打印日志和传参都更稳定。
	inp_path = Path(inp).expanduser()
	if not inp_path.is_absolute() and not inp_path.exists():
		inp_path = SWMM_DATA_DIR / inp_path
	inp_path = inp_path.resolve()
	# 这里只做两件最基本的校验：
	# 1. 文件必须存在
	# 2. 扩展名必须是 .inp
	if not inp_path.exists() or inp_path.suffix.lower() != ".inp":
		raise ValueError(f"Invalid INP file: {inp_path}")
	return inp_path


def run_swmm(runswmm_exe: Path, inp_path: Path, rpt_path: Path, out_path: Path) -> SwmmRunResult:
	"""调用外部 runswmm.exe 执行一次 SWMM 模拟，并返回结果对象。"""
	# SWMM 命令行调用顺序固定为：exe inp rpt out。
	# 这里把 Path 全部转为字符串，传给 subprocess 调用外部程序。
	cmd = [str(runswmm_exe), str(inp_path), str(rpt_path), str(out_path)]
	print("Running:")
	print("  " + " ".join(cmd))

	# capture_output=True 会抓取标准输出和标准错误，
	# 这样 Python 侧既能回显，也能把内容放进结果对象里。
	completed = subprocess.run(cmd, text=True, capture_output=True)
	# 如果 SWMM 输出了日志，这里原样打印，方便直接看模型运行信息。
	if completed.stdout:
		print(completed.stdout.rstrip())
	if completed.stderr:
		print(completed.stderr.rstrip(), file=sys.stderr)

	# 返回结构化结果对象，而不是只返回 exit code。
	# 这样主入口和其他脚本都能拿到完整上下文。
	return SwmmRunResult(
		inp_path=inp_path,
		rpt_path=rpt_path,
		out_path=out_path,
		exit_code=completed.returncode,
		stdout=completed.stdout,
		stderr=completed.stderr,
	)


def run_simulation(
	inp: str | Path,
	*,
	swmm_exe: str | None = None,
	rpt_name: str | None = None,
	out_name: str | None = None,
	force: bool = False,
) -> SwmmRunResult:
	"""执行一次完整的 SWMM 模拟，并返回结果对象。"""
	# 这一层是对外的主要调用接口。
	# 它把“校验输入”、“定位 exe”、“生成输出路径”、“处理覆盖逻辑”、“真正运行”串起来。
	inp_path = validate_inp_path(inp)
	runswmm_exe = resolve_runswmm(swmm_exe)
	rpt_path, out_path = build_output_paths(inp_path, rpt_name, out_name)

	# 如果结果文件已存在，默认不覆盖，避免误删历史结果。
	existing = [path for path in (rpt_path, out_path) if path.exists()]
	if existing and not force:
		existing_text = "\n".join(f"  - {path}" for path in existing)
		raise FileExistsError(
			"Output file(s) already exist:\n"
			f"{existing_text}\n"
			"Use force=True or pass --force to overwrite."
		)

	for path in existing:
		# force=True 时，先删除旧文件，再重新生成。
		path.unlink()

	return run_swmm(runswmm_exe, inp_path, rpt_path, out_path)
