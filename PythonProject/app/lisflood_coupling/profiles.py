"""LISFLOOD-specific study-area parameters, separate from SWMM model seeds."""

from dataclasses import dataclass

from app.lisflood_coupling.errors import LisfloodCouplingError


@dataclass(frozen=True)
class LisfloodProfile:
    study_area: str
    subcatchment_area_m2: float
    domain_area_m2: float

    @property
    def virtual_rainfall_scale(self) -> float:
        return self.subcatchment_area_m2 / self.domain_area_m2


LISFLOOD_PROFILES: dict[str, LisfloodProfile] = {
    "LC": LisfloodProfile("LC", 118_270_207.3, 150_174_375.0),
    "JJ": LisfloodProfile("JJ", 34_281_610.5, 63_401_875.0),
}


def get_lisflood_profile(study_area: str) -> LisfloodProfile:
    try:
        return LISFLOOD_PROFILES[study_area.strip().upper()]
    except KeyError as exc:
        raise LisfloodCouplingError(
            f"研究区 {study_area!r} 未配置 LISFLOOD 耦合参数"
        ) from exc
