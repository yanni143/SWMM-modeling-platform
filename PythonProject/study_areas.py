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

# SWMM RPT 的 Final Storage（mm）是各自 SWMM 汇水面积上的水深。LISFLOOD
# 虚拟降雨要施加在更大的二维计算域时，须乘以该面积比以保持水量不变。
# 面积单位均为 m²。
VIRTUAL_RAINFALL_DOMAINS: dict[str, dict[str, float]] = {
    "LC": {
        "subcatchment_area_m2": 118_270_207.3,
        "lisflood_domain_area_m2": 150_174_375.0,
    },
    "JJ": {
        "subcatchment_area_m2": 34_281_610.5,
        "lisflood_domain_area_m2": 63_401_875.0,
    },
}


def virtual_rainfall_scale(study_area: str) -> float:
    """Return the RPT-depth-to-LISFLOOD-domain depth scale for a study area."""
    area_key = study_area.strip().upper()
    try:
        domain = VIRTUAL_RAINFALL_DOMAINS[area_key]
    except KeyError as exc:
        raise ValueError(f"研究区 {study_area!r} 未配置 LISFLOOD 虚拟降雨面积") from exc
    return domain["subcatchment_area_m2"] / domain["lisflood_domain_area_m2"]


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
