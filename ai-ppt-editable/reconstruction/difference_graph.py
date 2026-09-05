#!/usr/bin/env python3
"""Executable difference graph produced by visual/object QA."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_DOMAINS = {"geometry", "typography", "asset", "hierarchy", "semantic"}
ALLOWED_SEVERITIES = {"P0", "P1", "P2", "P3"}


@dataclass(frozen=True)
class DifferenceFinding:
    id: str
    object_id: str
    domain: str
    severity: str
    message: str
    confidence: float = 1.0
    metrics: dict[str, Any] = field(default_factory=dict)
    proposed_patch: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DifferenceFinding":
        domain = str(data.get("domain", "")).strip()
        severity = str(data.get("severity", "P2")).strip().upper()
        if domain not in ALLOWED_DOMAINS:
            raise ValueError(f"unsupported difference domain: {domain!r}")
        if severity not in ALLOWED_SEVERITIES:
            raise ValueError(f"unsupported severity: {severity!r}")
        confidence = float(data.get("confidence", 1.0))
        if not 0 <= confidence <= 1:
            raise ValueError("difference confidence must be within [0, 1]")
        return cls(
            id=str(data.get("id") or f"{domain}:{data.get('object_id', 'unknown')}"),
            object_id=str(data.get("object_id", "")).strip(),
            domain=domain,
            severity=severity,
            message=str(data.get("message", "")).strip(),
            confidence=confidence,
            metrics=dict(data.get("metrics") or {}),
            proposed_patch=dict(data.get("proposed_patch") or {}),
            evidence=dict(data.get("evidence") or {}),
        )


@dataclass(frozen=True)
class DifferenceGraph:
    version: str
    source_id: str
    rendered_id: str
    findings: tuple[DifferenceFinding, ...]
    aggregate: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DifferenceGraph":
        graph = cls(
            version=str(data.get("version", "1.0")),
            source_id=str(data.get("source_id", "source")),
            rendered_id=str(data.get("rendered_id", "rendered")),
            findings=tuple(DifferenceFinding.from_dict(item) for item in (data.get("findings") or [])),
            aggregate=dict(data.get("aggregate") or {}),
            metadata=dict(data.get("metadata") or {}),
        )
        graph.validate()
        return graph

    def validate(self) -> None:
        ids = [item.id for item in self.findings]
        if len(ids) != len(set(ids)):
            raise ValueError("difference finding ids must be unique")
        for finding in self.findings:
            if not finding.object_id:
                raise ValueError(f"finding {finding.id}: object_id is required")
            if not finding.message:
                raise ValueError(f"finding {finding.id}: message is required")

    def unresolved(self, *, min_confidence: float = 0.0) -> tuple[DifferenceFinding, ...]:
        return tuple(item for item in self.findings if item.confidence >= min_confidence)

    def by_domain(self, domain: str) -> tuple[DifferenceFinding, ...]:
        return tuple(item for item in self.findings if item.domain == domain)

    def blocking(self) -> tuple[DifferenceFinding, ...]:
        return tuple(item for item in self.findings if item.severity in {"P0", "P1"})

    def quality_gate_passes(self, *, fail_on: tuple[str, ...] = ("P0", "P1")) -> bool:
        blocked = set(fail_on)
        return not any(item.severity in blocked for item in self.findings)
