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


# ---------------------------------------------------------------------------
# 虚拟降雨的“二维域面积”缩放表（main.py --LC / --JJ 用）
#
# 背景：汇水区地表滞蓄水（.rpt 的 Runoff Quantity Continuity -> Final Storage）
# 是**一维 SWMM 模型汇水面积**上的水量。把它交给二维模型时，如果降雨要撒在
# 更大的二维计算域上，就必须保持“水量不变、水深随面积变小”：
#
#     水量 = SWMM 汇水面积 × .rpt 水深      （不变量）
#     水深 = 水量 ÷ 二维域面积              （二维模型实际用的雨深）
#     缩放系数 = SWMM 汇水面积 ÷ 二维域面积
#
# 各区面积一律用 m2（SWMM 的 [SUBCATCHMENTS] 面积列单位是 ha，×10000 得 m2）。
#
#   key        label  subcatch_area_m2   domain_area_m2      缩放系数
#   LC(老城)   老城    118,270,207.3      150,174,375.0       0.7875519...
#   JJ(金江)   金江     34,281,610.5       63,401,875.0       0.5407029...
#
# 老城 subcatch_area_m2 = LC_MANUAL_23.inp 里 1158 个子汇水区面积之和
#                        （11827.0207 ha），与 .rpt 反算值差 -0.0007%。
# 金江 subcatch_area_m2 = JJ_MANUAL_7.inp 里 332 个子汇水区面积之和
#                        （3428.1610 ha）。
# domain_area_m2 由使用方给定（二维计算域面积），不是 SWMM 模型的量。
# ---------------------------------------------------------------------------
CHI_DOMAINS: dict[str, dict[str, object]] = {
    "LC": {
        "label": "老城",
        "subcatch_area_m2": 118_270_207.3,
        "domain_area_m2": 150_174_375.0,
    },
    "JJ": {
        "label": "金江",
        "subcatch_area_m2": 34_281_610.5,
        "domain_area_m2": 63_401_875.0,
    },
}