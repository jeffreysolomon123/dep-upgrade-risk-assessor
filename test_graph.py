from graph import build_graph

app = build_graph()

initial_state = {
    "package_name": "lucide-react",
    "current_version": "0.511.0",
    "target_version": "1.47.0",
    "bump_severity": "major",
    "repo_owner": None,
    "repo_name": None,
    "release_notes": None,
    "breaking_change_candidates": None,
    "changelog_source": None,
    "risk_label": None,
    "reasoning": None,
}

result = app.invoke(initial_state)

print("\n=== Final state ===")
print("changelog_source:", result["changelog_source"])
print("breaking_change_candidates:", result["breaking_change_candidates"])
print("reasoning:", result["reasoning"])