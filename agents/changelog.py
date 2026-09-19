import re
import requests
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_MAX_TOKENS, GITHUB_HEADERS
import json

_groq_client = Groq(api_key=GROQ_API_KEY)


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
        response = requests.get(url, headers=GITHUB_HEADERS, timeout=10)

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






def fetch_commit_diff_summary(owner: str, repo: str, current_version: str, target_version: str, package_name: str) -> str | None:
    """
    Try to get GitHub's compare view between two tags. Filters out
    low-signal commits (chores, docs, ci, tests) before returning,
    and only keeps commit subjects (not multi-line bodies) to keep
    the LLM context small and relevant.
    """
    candidates_current = [f"v{current_version}", current_version, f"{package_name}@{current_version}"]
    candidates_target = [f"v{target_version}", target_version, f"{package_name}@{target_version}"]

    noise_prefixes = ("chore:", "docs:", "test:", "ci:", "style:")
    noisy_file_patterns = ("lock", "test", ".md", ".yml", ".yaml")

    for c_tag in candidates_current:
        for t_tag in candidates_target:
            url = f"https://api.github.com/repos/{owner}/{repo}/compare/{c_tag}...{t_tag}"
            response = requests.get(url, headers=GITHUB_HEADERS, timeout=10)

            if response.status_code == 200:
                data = response.json()

                all_commits = [c["commit"]["message"].split("\n")[0] for c in data.get("commits", [])]
                relevant_commits = [
                    m for m in all_commits
                    if not m.lower().startswith(noise_prefixes)
                ][:30]

                all_files = [f["filename"] for f in data.get("files", [])]
                relevant_files = [
                    f for f in all_files
                    if not any(pattern in f.lower() for pattern in noisy_file_patterns)
                ][:30]

                if not relevant_commits and not relevant_files:
                    return None  # nothing signal-worthy — treat as no data

                return (
                    "Commit messages:\n" + "\n".join(f"- {m}" for m in relevant_commits) +
                    "\n\nChanged files:\n" + "\n".join(f"- {f}" for f in relevant_files)
                )

    print(f"  [warn] Could not fetch commit diff for {package_name} — no matching tag pair found or API error")
    return None

def summarize_likely_breaking_changes(
    package_name: str,
    current_version: str,
    target_version: str,
    diff_context: str | None,
) -> dict:
    """
    LLM call: given whatever context we have (a real diff summary, or
    just the version jump if we couldn't fetch one), ask the model to
    identify likely breaking changes. Returns structured JSON with an
    explicit confidence level so downstream logic knows how much to trust it.
    """
    # Skip the LLM entirely when we have nothing to reason from —
    # a canned low-confidence result is honest and costs zero tokens.
    if not diff_context:
        return {
            "likely_breaking_changes": [],
            "confidence": "low",
            "reasoning": "No commit or diff data was available, and this package/version jump was not called out as known-risky by pre-filtering.",
        }

    # Truncate BEFORE building the prompt, so it actually takes effect.
    if len(diff_context) > 4000:
        diff_context = diff_context[:4000] + "\n... (truncated)"

    context_block = f"Here is the commit/file-change context between the two versions:\n\n{diff_context}"

    prompt = f"""You are analyzing a dependency upgrade for likely breaking changes.

Package: {package_name}
Current version: {current_version}
Target version: {target_version}

{context_block}

You have real commit and file-change data — base your answer on it.

Respond ONLY with valid JSON in this exact shape, nothing else:
{{
  "likely_breaking_changes": ["short description 1", "short description 2"],
  "confidence": "high" | "medium" | "low",
  "reasoning": "one or two sentences explaining your confidence level"
}}

If you found no likely breaking changes, return an empty list for likely_breaking_changes, not a made-up one."""

    try:
        response = _groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=GROQ_MAX_TOKENS,
        )
    except Exception as e:
        print("\n--- DEBUG: prompt that failed ---")
        print(prompt)
        print("--- DEBUG: error ---")
        print(e)
        print("--- END DEBUG ---\n")
        raise

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "likely_breaking_changes": [],
            "confidence": "low",
            "reasoning": "LLM response could not be parsed as JSON",
        }