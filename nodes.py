from state import DependencyState
from agents.changelog import (
    get_repo_info,
    fetch_release_notes,
    parse_structured_breaking_changes,
    is_structured_and_reliable,
    fetch_commit_diff_summary,
    summarize_likely_breaking_changes,
)


def changelog_node(state: DependencyState) -> DependencyState:
    package_name = state["package_name"]
    version = state["target_version"]

    repo_info = get_repo_info(package_name)

    if repo_info is None:
        return {
            **state,
            "repo_owner": None,
            "repo_name": None,
            "release_notes": None,
            "breaking_change_candidates": None,
            "changelog_source": "none",
            "reasoning": "Could not locate a GitHub repository for this package.",
        }
    notes = fetch_release_notes(
        repo_info["owner"], repo_info["repo"], version, package_name=package_name
    )
    breaking = parse_structured_breaking_changes(notes) if notes else None
    trustworthy = is_structured_and_reliable(notes, breaking)

    if trustworthy:
        reasoning = (
            f"Found {len(breaking)} documented breaking change(s) in structured release notes."
            if breaking else
            "Release notes were structured and did not indicate any breaking changes."
        )
    else:
        reasoning = None  # will be filled in by diff_fallback_node instead

    return {
        **state,
        "repo_owner": repo_info["owner"],
        "repo_name": repo_info["repo"],
        "release_notes": notes,
        "breaking_change_candidates": breaking,
        "changelog_source": "structured" if trustworthy else "needs_fallback",
        "reasoning": reasoning,
    }


def route_after_changelog(state: DependencyState) -> str:
    if state["changelog_source"] == "structured":
        return "trustworthy"
    return "needs_fallback"


def diff_fallback_node(state: DependencyState) -> DependencyState:
    """
    Real diff-fallback logic: try to get commit/file-change context from
    GitHub, then ask the LLM to summarize likely breaking changes from it
    (or from general knowledge, honestly flagged as low confidence, if
    no diff data could be retrieved).
    """
    package_name = state["package_name"]
    owner = state.get("repo_owner")
    repo = state.get("repo_name")

    diff_context = None
    if owner and repo:
        diff_context = fetch_commit_diff_summary(
            owner, repo, state["current_version"], state["target_version"], package_name
        )

    result = summarize_likely_breaking_changes(
        package_name, state["current_version"], state["target_version"], diff_context
    )

    return {
        **state,
        "breaking_change_candidates": result["likely_breaking_changes"],
        "changelog_source": "diff_fallback",
        "reasoning": result["reasoning"],
    }