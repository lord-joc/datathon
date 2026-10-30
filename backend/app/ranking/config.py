"""Profiles (config/profiles.json) and formula constants (config/ranking_config.json).

Both files are versioned configuration, not code (ADR16). A profile's identity is the
SHA-256 of its canonical config, which also includes the formula constants, so changing
a weight or a threshold always produces a new profile version.
"""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

CRITERIA = (
    "transit",
    "universities",
    "culture",
    "parking",
    "schools",
    "area",
    "street",
    "competition",
    "cost",
)


@dataclass(frozen=True)
class RankingConstants:
    version: str
    transit_zero_m: Decimal
    parking_zero_m: Decimal
    university_cap: Decimal
    culture_cap: Decimal
    school_cap: Decimal
    other_position_utility: Decimal
    competition_density_scale_km2: Decimal
    precision_digits: int
    status_validity_hours: int
    confirmation_ttl_s: int
    ranking_ttl_days: int
    raw: dict[str, Any]


@dataclass(frozen=True)
class Profile:
    code: str
    name: str
    summary: str
    icon: str
    target_area_m2: Decimal
    weights: dict[str, Decimal]
    competitor_tags: dict[str, list[str]] | None
    version_label: str
    config: dict[str, Any]
    config_sha256: str


@dataclass(frozen=True)
class ProfileSet:
    version: str
    constants: RankingConstants
    profiles: dict[str, Profile]

    def get(self, code: str) -> Profile:
        try:
            return self.profiles[code]
        except KeyError:
            raise KeyError(f"Nepoznat profil: {code}") from None


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _dec(raw: dict[str, Any], key: str) -> Decimal:
    return Decimal(str(raw[key]))


def load_constants(config_dir: Path) -> RankingConstants:
    raw = json.loads((config_dir / "ranking_config.json").read_text(encoding="utf-8"))
    raw.pop("$comment", None)
    return RankingConstants(
        version=str(raw["version"]),
        transit_zero_m=_dec(raw, "transit_zero_m"),
        parking_zero_m=_dec(raw, "parking_zero_m"),
        university_cap=_dec(raw, "university_cap"),
        culture_cap=_dec(raw, "culture_cap"),
        school_cap=_dec(raw, "school_cap"),
        other_position_utility=_dec(raw, "other_position_utility"),
        competition_density_scale_km2=_dec(raw, "competition_density_scale_km2"),
        precision_digits=int(raw["precision_digits"]),
        status_validity_hours=int(raw["status_validity_hours"]),
        confirmation_ttl_s=int(raw["comparison_confirmation_ttl_s"]),
        ranking_ttl_days=int(raw["ranking_ttl_days"]),
        raw=raw,
    )


def load_profiles(config_dir: Path) -> ProfileSet:
    constants = load_constants(config_dir)
    raw = json.loads((config_dir / "profiles.json").read_text(encoding="utf-8"))
    if tuple(raw["criteria"]) != CRITERIA:
        raise ValueError("profiles.json: popis kriterija ne odgovara kodu rangiranja.")
    version = str(raw["version"])
    profiles: dict[str, Profile] = {}
    for entry in raw["profiles"]:
        weights = entry["weights"]
        if set(weights) != set(CRITERIA):
            raise ValueError(f"profiles.json: profil {entry['code']} nema sve kriterije.")
        if any(not 0 <= w <= 100 for w in weights.values()) or sum(weights.values()) != 100:
            raise ValueError(
                f"profiles.json: težine profila {entry['code']} nisu 0-100 sa zbrojem 100."
            )
        config = {"profile": entry, "profiles_version": version, "ranking": constants.raw}
        profiles[entry["code"]] = Profile(
            code=entry["code"],
            name=entry["name"],
            summary=entry.get("summary", ""),
            icon=entry.get("icon", ""),
            target_area_m2=Decimal(str(entry["target_area_m2"])),
            weights={k: Decimal(str(weights[k])) for k in CRITERIA},
            competitor_tags=entry.get("competitor_tags"),
            version_label=version,
            config=config,
            config_sha256=hashlib.sha256(canonical(config).encode()).hexdigest(),
        )
    return ProfileSet(version=version, constants=constants, profiles=profiles)
