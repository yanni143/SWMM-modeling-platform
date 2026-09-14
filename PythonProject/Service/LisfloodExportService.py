"""Produce the current scheme-three LISFLOOD point-flow artifact."""

from __future__ import annotations

from pathlib import Path

from swmm_core.lisflood_rate import build_without_sub, write_output
from swmm_core.rpt_coupling import build_without_sub_source_data


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
