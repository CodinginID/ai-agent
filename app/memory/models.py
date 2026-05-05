from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Project:
    id: str
    name: str
    root_path: str
    description: str
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "root_path": self.root_path,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Project:
        return cls(
            id=data["id"],
            name=data["name"],
            root_path=data.get("root_path", "."),
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
