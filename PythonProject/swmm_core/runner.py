import os
from pathlib import Path
from pyswmm import Simulation


def run_pyswmm(inp_path: str) -> dict:
    inp_file = Path(inp_path).resolve()

    if not inp_file.exists():
        raise FileNotFoundError(f"找不到 inp 文件: {inp_file}")

    workdir = inp_file.parent
    print(f"工作目录: {workdir}")
    print(f"运行文件: {inp_file.name}")

    # 切到 inp 所在目录，避免相对路径问题
    previous_workdir = Path.cwd()
    try:
        os.chdir(workdir)
        with Simulation(str(inp_file)) as sim:
            print("开始运行 PySWMM...")
            for _ in sim:
                pass
            print("PySWMM 运行完成。")
    finally:
        os.chdir(previous_workdir)

    rpt_file = inp_file.with_suffix(".rpt")
    out_file = inp_file.with_suffix(".out")

    print(f"RPT 文件存在: {rpt_file.exists()} -> {rpt_file}")
    print(f"OUT 文件存在: {out_file.exists()} -> {out_file}")

    return {
        "success": True,
        "message": "PySWMM 运行完成",
        "inp_file": str(inp_file),
        "rpt_file": str(rpt_file),
        "out_file": str(out_file),
        "rpt_exists": rpt_file.exists(),
        "out_exists": out_file.exists(),
    }


if __name__ == "__main__":
    run_pyswmm(r"E:/SWMM_LLM/PythonProject_data/20260327_212543/model.inp")
