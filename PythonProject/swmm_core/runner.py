import logging
import os
import threading
from pathlib import Path

from pyswmm import Simulation

logger = logging.getLogger(__name__)
_simulation_lock = threading.Lock()


def run_pyswmm(inp_path: str) -> dict:
    inp_file = Path(inp_path).resolve()

    if not inp_file.exists():
        raise FileNotFoundError(f"找不到 inp 文件: {inp_file}")

    workdir = inp_file.parent
    logger.info("开始运行 SWMM：%s", inp_file)
    # PySWMM 运行时可能解析 INP 中的相对路径，而 os.chdir 会影响整个进程，
    # 因此同一 worker 内串行执行，避免并发模拟互相切换工作目录。
    with _simulation_lock:
        previous_workdir = Path.cwd()
        try:
            os.chdir(workdir)
            with Simulation(str(inp_file)) as sim:
                for _ in sim:
                    pass
        finally:
            os.chdir(previous_workdir)

    rpt_file = inp_file.with_suffix(".rpt")
    out_file = inp_file.with_suffix(".out")

    logger.info("SWMM 运行完成：out=%s, rpt=%s", out_file.exists(), rpt_file.exists())

    return {
        "success": True,
        "message": "PySWMM 运行完成",
        "inp_file": str(inp_file),
        "rpt_file": str(rpt_file),
        "out_file": str(out_file),
        "rpt_exists": rpt_file.exists(),
        "out_exists": out_file.exists(),
    }
