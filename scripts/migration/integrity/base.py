from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class CheckResult:
    domain: str
    severity: str
    key: str
    field: str
    message: str
    firebase_value: Any = None
    sql_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def max_severity(results: list[CheckResult]) -> str:
    if not results:
        return "ok"
    return max(results, key=lambda item: SEVERITY_ORDER.get(item.severity, 0)).severity


def should_fail(results: list[CheckResult], fail_on: str) -> bool:
    threshold = SEVERITY_ORDER.get(fail_on, SEVERITY_ORDER["high"])
    return any(SEVERITY_ORDER.get(item.severity, 0) >= threshold for item in results)
