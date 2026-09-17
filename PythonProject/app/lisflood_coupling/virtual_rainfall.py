"""Convert SWMM runoff final storage into a LISFLOOD virtual rainfall file."""

from pathlib import Path

from app.lisflood_coupling.input import LisfloodInput
from app.lisflood_coupling.profiles import get_lisflood_profile
from app.swmm.inp import load_inp_context
from app.swmm.rpt import read_runoff_final_storage
from Tools.InpTools.ChicagoRainfall import DEFAULT_DATE, write_chicago_file


def write_virtual_rainfall(coupling_input: LisfloodInput) -> Path | None:
    """Write virtual rainfall, or return ``None`` when RPT storage is absent."""
    source = coupling_input.normalized()
    _, final_storage_mm = read_runoff_final_storage(source.rpt_path)
    if final_storage_mm is None or final_storage_mm <= 0:
        return None

    context = load_inp_context(source.inp_path)
    profile = get_lisflood_profile(source.study_area)
    date_str = context.info.options.get("START_DATE", DEFAULT_DATE)
    output = source.output_dir / f"chi_{source.case_name}.txt"
    return write_chicago_file(
        context.info.sim_hours,
        final_storage_mm * profile.virtual_rainfall_scale,
        output,
        date_str=date_str,
    )
