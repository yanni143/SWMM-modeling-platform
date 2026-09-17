"""Single public entry point for a SWMM-to-LISFLOOD conversion."""

from app.lisflood_coupling.input import LisfloodExportResult, LisfloodInput
from app.lisflood_coupling.point_flooding import build_point_flooding, write_point_flooding
from app.lisflood_coupling.virtual_rainfall import write_virtual_rainfall


class LisfloodExporter:
    """Produce the two existing LISFLOOD artifacts without storage or API access."""

    def export(self, coupling_input: LisfloodInput) -> LisfloodExportResult:
        source = coupling_input.normalized()
        point_flooding_path = write_point_flooding(
            build_point_flooding(source),
            source.output_dir / f"rate_{source.case_name}_without_sub.json",
        )
        return LisfloodExportResult(
            point_flooding_path=point_flooding_path,
            virtual_rainfall_path=write_virtual_rainfall(source),
        )
