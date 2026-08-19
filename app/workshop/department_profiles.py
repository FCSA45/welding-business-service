"""Department configuration and knowledge-folder discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "workshop"


@dataclass(frozen=True)
class DepartmentProfile:
    code: str
    name: str
    important_large_centimeters: float = 1000.0
    example_limit: int = 3
    knowledge_dir: Path | None = None


class DepartmentProfileRegistry:
    """Load optional per-department rules while keeping unknown departments usable."""

    def __init__(self, root: str | Path = DEFAULT_KNOWLEDGE_ROOT) -> None:
        self.root = Path(root).resolve()
        self._profiles = self._load_profiles()

    def resolve(self, department: str) -> DepartmentProfile:
        name = department.strip()
        if not name:
            raise ValueError("department is required")
        profile = self._profiles.get(name)
        if profile is not None:
            return profile
        return DepartmentProfile(code=name, name=name, knowledge_dir=None)

    def list(self) -> tuple[DepartmentProfile, ...]:
        return tuple(sorted(self._profiles.values(), key=lambda item: item.name))

    def shared_knowledge_dir(self) -> Path:
        return self.root / "shared"

    def knowledge_files(self, department: str) -> tuple[Path, ...]:
        profile = self.resolve(department)
        roots = [self.shared_knowledge_dir()]
        if profile.knowledge_dir is not None:
            roots.append(profile.knowledge_dir)
        return tuple(
            path for root in roots if root.is_dir()
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.name != "department.json"
        )

    def _load_profiles(self) -> dict[str, DepartmentProfile]:
        profiles: dict[str, DepartmentProfile] = {}
        departments_root = self.root / "departments"
        if not departments_root.is_dir():
            return profiles
        for config_path in sorted(departments_root.glob("*/department.json")):
            values = json.loads(config_path.read_text(encoding="utf-8"))
            profile = DepartmentProfile(
                code=str(values["code"]).strip(),
                name=str(values["name"]).strip(),
                important_large_centimeters=float(values.get("important_large_centimeters", 1000)),
                example_limit=max(1, min(10, int(values.get("example_limit", 3)))),
                knowledge_dir=config_path.parent,
            )
            if profile.name in profiles:
                raise ValueError(f"duplicate department profile: {profile.name}")
            profiles[profile.name] = profile
        return profiles
