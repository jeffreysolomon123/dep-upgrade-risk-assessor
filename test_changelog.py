from agents.changelog import (
    get_repo_info,
    fetch_release_notes,
    parse_structured_breaking_changes,
    is_structured_and_reliable,
)

package = "lucide-react"
version = "1.47.0"

repo_info = get_repo_info(package)
print("Repo info:", repo_info)

if repo_info:
    notes = fetch_release_notes(repo_info["owner"], repo_info["repo"], version, package_name=package)
    breaking = parse_structured_breaking_changes(notes) if notes else None
    trustworthy = is_structured_and_reliable(notes, breaking)

    print("\nParsed breaking changes:", breaking)
    print("Trustworthy structured result?", trustworthy)
    print("→ Route to:", "Risk-Matching" if trustworthy else "Diff Fallback")