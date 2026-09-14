"""Produce the current scheme-three LISFLOOD point-flow artifact."""

from __future__ import annotations

from pathlib import Path

from swmm_core.lisflood_rate import build_without_sub, write_output
from swmm_core.rpt_coupling import (
    build_without_sub_source_data,
    load_inp,
    read_runoff_final_storage,
)
from Tools.InpTools.ChicagoRainfall import write_chicago_file


class LisfloodExportService:
    """Export RPT-only overflow rates without re-running SWMM."""

    def write_without_sub(
        self, inp_path: str | Path, rpt_path: str | Path, output_dir: str | Path, case_name: str
    ) -> Path:
        source = build_without_sub_source_data(inp_path, rpt_path)
        rate_rows, _ = build_without_sub(source)
        output = Path(output_dir) / f"rate_{case_name}_without_sub.json"
        write_output(rate_rows, output)
        return output

    def write_virtual_rainfall(
        self, inp_path: str | Path, rpt_path: str | Path, output_dir: str | Path, case_name: str
    ) -> Path | None:
        """Create scheme-three virtual rainfall from RPT runoff final storage.

        A missing or non-positive final-storage depth means no virtual rainfall is
        available for this run.  The point-source artifact remains valid and is
        deliberately not affected.
        """
        _, final_storage_mm = read_runoff_final_storage(rpt_path)
        if final_storage_mm is None or final_storage_mm <= 0:
            return None

        inp = load_inp(inp_path)
        date_str = inp.options.get("START_DATE", "07/15/2025")
        output = Path(output_dir) / f"chi_{case_name}.txt"
        return write_chicago_file(
            inp.sim_hours, final_storage_mm, output, date_str=date_str
        )
