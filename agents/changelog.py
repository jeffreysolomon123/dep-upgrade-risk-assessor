import re
import requests


def get_repo_info(package_name: str) -> dict | None:
    """
    Fetch a package's full npm metadata and extract its GitHub repo
    (owner, repo name) so we can look up release notes.
    """
    url = f"https://registry.npmjs.org/{package_name}"
    response = requests.get(url, timeout=10)

    if response.status_code != 200:
        return None

    data = response.json()
    repo_field = data.get("repository")

    if not repo_field:
        return None

    # repository can be a string or a dict like {"type": "git", "url": "..."}
    repo_url = repo_field if isinstance(repo_field, str) else repo_field.get("url", "")

    # Normalize things like "git+https://github.com/owner/repo.git" or
    # "github:owner/repo" down to owner/repo
    match = re.search(r"github\.com[/:]([^/]+)/([^/.]+)", repo_url)
    if not match:
        match = re.search(r"github:([^/]+)/([^/]+)", repo_url)

    if not match:
        return None

    return {"owner": match.group(1), "repo": match.group(2)}


def fetch_release_notes(owner: str, repo: str, version: str, package_name: str = None) -> str | None:
    """
    Try to fetch GitHub release notes for a specific version.
    Tag naming is genuinely inconsistent across projects:
    - simple repos: 'v1.2.3' or '1.2.3'
    - monorepos: 'packagename@1.2.3' or 'packagename-v1.2.3'
    Try the common patterns before giving up.
    """
    candidates = [f"v{version}", version]

    if package_name:
        candidates.extend([
            f"{package_name}@{version}",
            f"{package_name}-v{version}",
            f"{package_name}-{version}",
        ])

    for tag in candidates:
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            return data.get("body")

    return None

def parse_structured_breaking_changes(release_notes: str) -> list[str] | None:
    """
    Attempt to extract a 'Breaking Changes' section from clean,
    structured release notes (Keep a Changelog style).

    Returns a list of breaking-change bullet lines if found,
    or None if the notes don't follow a recognizable structure
    (signal to the caller: fall back to diff-reading instead).
    """
    if not release_notes:
        return None

    # Look for a markdown heading containing "breaking"
    # e.g. "### Breaking Changes", "## BREAKING CHANGE", "### 💥 Breaking"
    heading_pattern = re.compile(
        r"^#{1,4}.*breaking.*$", re.IGNORECASE | re.MULTILINE
    )

    match = heading_pattern.search(release_notes)
    if not match:
        return None

    # Grab everything from that heading until the next heading of the
    # same or higher level, or end of text
    start = match.end()
    next_heading = re.search(r"^#{1,4}\s", release_notes[start:], re.MULTILINE)
    section_text = release_notes[start: start + next_heading.start()] if next_heading else release_notes[start:]

    # Extract bullet points from that section
    bullets = re.findall(r"^\s*[-*]\s+(.+)$", section_text, re.MULTILINE)

    if not bullets:
        return None

    return [b.strip() for b in bullets]



def is_structured_and_reliable(release_notes: str | None, parsed_breaking: list[str] | None) -> bool:
    """
    Decide whether we can trust the structured parse, or whether this
    should fall back to diff-reading instead.

    Returns False (→ fallback) when:
    - there were no release notes at all
    - we found a breaking-changes section (parsed_breaking is truthy) — trust it
    - the notes look like GitHub's auto-generated 'What's Changed' format,
      which lists PRs but doesn't reliably document breaking changes
    """
    if release_notes is None:
        return False

    if parsed_breaking:
        return True  # we found and parsed an actual breaking-changes section

    # Detect GitHub's auto-generated format — a strong signal that a
    # missing "breaking changes" section doesn't mean there were none,
    # it means this format never states it clearly
    if "## What's Changed" in release_notes or "**Full Changelog**" in release_notes:
        return False

    # No breaking section, and it's not the auto-generated format either —
    # could genuinely be a clean release with no breaking changes
    return True