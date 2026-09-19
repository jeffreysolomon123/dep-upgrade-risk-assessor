import json
import time
from agents.scanner import scan_dependencies, filter_for_investigation
from graph import build_graph


def load_package_json(path: str) -> dict:
    with open(path, "r") as f:
        data = json.load(f)
    return data.get("dependencies", {})


def make_initial_state(pkg: dict) -> dict:
    """
    Build the initial DependencyState for a queued package. Note:
    for packages tagged 'unparseable' (like 'latest'), we don't have
    a real current_version to diff against — we'll pass it through
    as-is and let the pipeline handle it (it should gracefully fall
    back since diffing 'latest' against a real version won't resolve
    to a valid tag anyway).
    """
    return {
        "package_name": pkg["name"],
        "current_version": pkg["current_version"],
        "target_version": pkg["latest_version"],
        "bump_severity": pkg["bump_severity"],
        "repo_owner": None,
        "repo_name": None,
        "release_notes": None,
        "breaking_change_candidates": None,
        "changelog_source": None,
        "risk_label": None,
        "reasoning": None,
    }


if __name__ == "__main__":
    deps = load_package_json("package.json")
    scan_results = scan_dependencies(deps)
    queued = filter_for_investigation(scan_results)

    app = build_graph()

    print(f"Running full pipeline on {len(queued)} queued dependencies...\n")

    results = []
    for pkg in queued:
        print(f"--- {pkg['name']} ({pkg['current_version']} → {pkg['latest_version']}) ---")
        initial_state = make_initial_state(pkg)

        try:
            result = app.invoke(initial_state)
            results.append(result)

            print(f"  source: {result['changelog_source']}")
            print(f"  breaking changes: {result['breaking_change_candidates']}")
            print(f"  reasoning: {result['reasoning']}")
        except Exception as e:
            print(f"  ERROR: {e}")

        print()
        time.sleep(1)  # be polite to GitHub's unauthenticated rate limit

    print("=== Summary ===")
    for r in results:
        count = len(r["breaking_change_candidates"] or [])
        print(f"{r['package_name']}: {count} likely breaking change(s) via {r['changelog_source']}")