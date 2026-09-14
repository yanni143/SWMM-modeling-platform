from __future__ import annotations

"""项目级配置。

这个模块目前负责集中管理当前项目约定好的目录与文件路径
"""

from pathlib import Path


# tools 目录。
TOOLS_DIR = Path(__file__).resolve().parent

# 仓库根目录。
REPO_ROOT = TOOLS_DIR.parent

# 第三方可执行文件目录。
BIN_DIR = REPO_ROOT / "bin"
RUNSWMM_EXE = BIN_DIR / "runswmm.exe"
SWMM_DLL = BIN_DIR / "swmm5.dll"

# 数据目录。
DATA_DIR = REPO_ROOT / "data"
SWMM_DATA_DIR = DATA_DIR / "swmm"
RESULTS_DIR = DATA_DIR / "results"