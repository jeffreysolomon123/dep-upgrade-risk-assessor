import requests


def get_latest_version(package_name: str) -> str | None:
    """Query the npm registry for a package's latest published version."""
    url = f"https://registry.npmjs.org/{package_name}/latest"
    response = requests.get(url, timeout=10)

    if response.status_code != 200:
        return None

    data = response.json()
    return data.get("version")


def classify_bump(current: str, latest: str) -> str | None:
    """
    Compare two semver strings and classify the jump as major/minor/patch.
    Returns None if either version can't be parsed (e.g., 'latest', 'workspace:*').
    """
    def parse(v: str) -> tuple[int, int, int] | None:
        parts = v.split(".")
        if len(parts) < 3:
            return None
        try:
            return tuple(int(p) for p in parts[:3])
        except ValueError:
            return None

    current_parsed = parse(current)
    latest_parsed = parse(latest)

    if current_parsed is None or latest_parsed is None:
        return None  # unparseable — flag separately, don't guess

    c_major, c_minor, c_patch = current_parsed
    l_major, l_minor, l_patch = latest_parsed

    if l_major != c_major:
        return "major"
    if l_minor != c_minor:
        return "minor"
    if l_patch != c_patch:
        return "patch"
    return None  # identical


def scan_dependencies(package_json_deps: dict) -> list[dict]:
    """
    Given the 'dependencies' dict from package.json, return a list of
    packages that have a newer version available, each tagged with
    bump severity so downstream agents can prioritize what to investigate.
    """
    results = []

    for name, current_version_spec in package_json_deps.items():
        current_version = current_version_spec.lstrip("^~>=<")

        latest_version = get_latest_version(name)

        if latest_version is None:
            results.append({
                "name": name,
                "current_version": current_version,
                "latest_version": None,
                "bump_severity": "unknown",
                "note": "could not fetch latest version from npm",
            })
            continue

        if current_version == latest_version:
            continue  # already up to date, nothing to report

        severity = classify_bump(current_version, latest_version)

        if severity is None:
            # covers both "unparseable version" (e.g. 'latest') and
            # 'identical after parsing' edge cases
            results.append({
                "name": name,
                "current_version": current_version,
                "latest_version": latest_version,
                "bump_severity": "unparseable",
                "note": f"could not classify version jump ('{current_version}' vs '{latest_version}')",
            })
            continue

        results.append({
            "name": name,
            "current_version": current_version,
            "latest_version": latest_version,
            "bump_severity": severity,
            "note": None,
        })

    return results


def filter_for_investigation(scan_results: list[dict]) -> list[dict]:
    """
    Decide which scanned dependencies are actually worth the expensive
    changelog + AST investigation pipeline.

    Policy: skip only what semver guarantees is safe (patch, and for now
    minor). Everything else — major bumps, and anything we couldn't even
    classify — gets queued for investigation, because we have no basis
    to assume it's safe.
    """
    queued = []

    for pkg in scan_results:
        severity = pkg["bump_severity"]

        if severity in ("patch", "minor"):
            continue  # semver says this shouldn't contain breaking changes

        # major, unparseable, unknown — all get investigated
        queued.append(pkg)

    return queued