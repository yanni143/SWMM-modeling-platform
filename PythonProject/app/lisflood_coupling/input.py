"""File-system input and output types for one LISFLOOD conversion."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LisfloodInput:
    """Dynamic RPT result plus immutable SWMM model context for one conversion."""

    inp_path: Path
    rpt_path: Path
    study_area: str
    case_name: str
    output_dir: Path

    def normalized(self) -> "LisfloodInput":
        return LisfloodInput(
            inp_path=Path(self.inp_path).expanduser().resolve(),
            rpt_path=Path(self.rpt_path).expanduser().resolve(),
            study_area=self.study_area.strip().upper(),
            case_name=self.case_name,
            output_dir=Path(self.output_dir).expanduser().resolve(),
        )


@dataclass(frozen=True)
class LisfloodExportResult:
    """Files created by the conversion; rainfall is absent when storage is zero."""

    point_flooding_path: Path
    virtual_rainfall_path: Path | None
