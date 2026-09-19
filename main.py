import json
from agents.scanner import scan_dependencies, filter_for_investigation

def load_package_json(path: str) -> dict:
    with open(path, "r") as f:
        data = json.load(f)
    return data.get("dependencies", {})


if __name__ == "__main__":
    deps = load_package_json("package.json")
    results = scan_dependencies(deps)

    print("=== All outdated dependencies ===")
    for pkg in results:
        severity = pkg["bump_severity"]
        line = f"[{severity.upper()}] {pkg['name']}: {pkg['current_version']} → {pkg['latest_version']}"
        if pkg.get("note"):
            line += f"  ⚠ {pkg['note']}"
        print(line)

    queued = filter_for_investigation(results)

    print(f"\n=== Queued for investigation ({len(queued)} of {len(results)}) ===")
    for pkg in queued:
        print(f"[{pkg['bump_severity'].upper()}] {pkg['name']}")