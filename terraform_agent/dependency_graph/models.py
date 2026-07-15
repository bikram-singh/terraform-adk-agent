from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any

@dataclass(frozen=True)
class DependencyNode:
    id: str
    service: str
    resource_type: str
    purpose: str
    required: bool = True
    implementation_status: str = "planned"
    generator_service: str | None = None
    configuration: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class DependencyEdge:
    source: str
    target: str
    relationship: str
    def to_dict(self) -> dict[str, str]:
        return asdict(self)

@dataclass(frozen=True)
class ArchitectureGraph:
    architecture_type: str
    nodes: tuple[DependencyNode, ...]
    edges: tuple[DependencyEdge, ...]
    warnings: tuple[str, ...] = ()
    @property
    def unsupported_required_nodes(self) -> tuple[DependencyNode, ...]:
        return tuple(
            n for n in self.nodes
            if n.required and n.implementation_status != "available"
        )
    @property
    def can_generate_complete_project(self) -> bool:
        return not self.unsupported_required_nodes
    def to_dict(self) -> dict[str, Any]:
        return {
            "architecture_type": self.architecture_type,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "warnings": list(self.warnings),
            "can_generate_complete_project": self.can_generate_complete_project,
            "unsupported_required_nodes": [
                n.to_dict() for n in self.unsupported_required_nodes
            ],
        }
