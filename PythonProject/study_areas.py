"""Built-in SWMM study-area definitions.

The application deliberately seeds these models from its own resources instead
of importing anything from the historical ``runswmm`` reference directory.
"""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True)
class StudyAreaSeed:
    model_id: UUID
    version_id: UUID
    name: str
    description: str
    dataset_id: str
    inp_path: Path


_RESOURCE_DIR = Path(__file__).resolve().parent / "resources" / "study_areas"


STUDY_AREA_SEEDS: tuple[StudyAreaSeed, ...] = (
    StudyAreaSeed(
        model_id=UUID("10000000-0000-0000-0000-000000000001"),
        version_id=UUID("10000000-0000-0000-0000-000000000101"),
        name="LC",
        description="LC_MANUAL_23 SWMM 研究区",
        dataset_id="LC_MANUAL_23",
        inp_path=_RESOURCE_DIR / "lc" / "model.inp",
    ),
    StudyAreaSeed(
        model_id=UUID("20000000-0000-0000-0000-000000000001"),
        version_id=UUID("20000000-0000-0000-0000-000000000101"),
        name="JJ",
        description="JJ_MANUAL_7 SWMM 研究区",
        dataset_id="JJ_MANUAL_7",
        inp_path=_RESOURCE_DIR / "jj" / "model.inp",
    ),
)
