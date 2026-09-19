from typing import TypedDict, Optional


class DependencyState(TypedDict):
    package_name: str
    current_version: str
    target_version: str
    bump_severity: str          # major / minor / patch / unparseable / unknown

    repo_owner: Optional[str]
    repo_name: Optional[str]

    release_notes: Optional[str]
    breaking_change_candidates: Optional[list[str]]
    changelog_source: Optional[str]    # "structured" | "diff_fallback" | "none"

    risk_label: Optional[str]          # safe / needs-review / high-risk
    reasoning: Optional[str]