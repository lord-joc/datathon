"""Load config/profiles.json into criteria_profile (insert-only, one row per config hash).

A ranking run references the exact profile version it used, so a profile row is never
updated. Changing a weight or a formula constant needs a new "version" in profiles.json;
the same label with different content is refused instead of silently overwritten.
"""

from sqlalchemy import Connection, text

from app.ranking.config import ProfileSet, canonical


class ProfileVersionError(Exception):
    pass


def sync_profiles(conn: Connection, profiles: ProfileSet) -> int:
    created = 0
    for p in profiles.profiles.values():
        clash = conn.execute(
            text(
                "SELECT config_sha256 FROM prostoriq.criteria_profile "
                "WHERE profile_code = :c AND version_label = :v"
            ),
            {"c": p.code, "v": p.version_label},
        ).scalar_one_or_none()
        if clash is not None:
            if clash != p.config_sha256:
                raise ProfileVersionError(
                    f"Profil {p.code} verzije {p.version_label} već postoji s drugim težinama "
                    "ili konstantama. Povećaj 'version' u config/profiles.json."
                )
            continue
        conn.execute(
            text(
                """
                INSERT INTO prostoriq.criteria_profile (profile_code, version_label,
                    config_sha256, weights, target_area_m2, config)
                VALUES (:c, :v, :sha, CAST(:w AS jsonb), :t, CAST(:cfg AS jsonb))
                """
            ),
            {
                "c": p.code,
                "v": p.version_label,
                "sha": p.config_sha256,
                "w": canonical({k: float(v) for k, v in p.weights.items()}),
                "t": p.target_area_m2,
                "cfg": canonical(p.config),
            },
        )
        created += 1
    return created
