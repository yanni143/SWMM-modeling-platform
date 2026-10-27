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

# A second immutable input root for JJ, sharing its study area but not its INP.
JJ_REAL_VERSION_ID = UUID("20000000-0000-0000-0000-000000000102")
JJ_REAL_INPUT_PATH = _RESOURCE_DIR.parent / "rainfall" / "jj" / "JJ_real_20260913_2d.inp"


def rainfall_inputs(model_id: UUID) -> list[dict]:
    seed = next(seed for seed in STUDY_AREA_SEEDS if seed.model_id == model_id)
    inputs = [
        {
            "mode": "design",
            "label": "模拟降雨",
            "baseline_version_id": seed.version_id,
            "filename": seed.inp_path.name,
        }
    ]
    if seed.name == "JJ":
        inputs.append(
            {
                "mode": "real",
                "label": "真实降雨（20260913）",
                "baseline_version_id": JJ_REAL_VERSION_ID,
                "filename": JJ_REAL_INPUT_PATH.name,
            }
        )
    return inputs
