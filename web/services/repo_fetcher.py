from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class RepositoryError(RuntimeError):
    """Raised when repository parsing or fetching fails."""


@dataclass(frozen=True, slots=True)
class GitHubRepoRef:
    owner: str
    repo: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def local_key(self) -> str:
        return f"{self.owner}__{self.repo}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}.git"


def parse_github_repo(value: str) -> GitHubRepoRef:
    raw = (value or "").strip()
    if not raw:
        raise RepositoryError("GitHub repository URL is required.")

    if raw.startswith("git@github.com:"):
        tail = raw[len("git@github.com:") :]
    else:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        if parsed.netloc.lower() != "github.com":
            raise RepositoryError("Only github.com repositories are supported in this version.")
        tail = parsed.path.lstrip("/")

    if tail.endswith(".git"):
        tail = tail[:-4]
    tail = tail.strip("/")
    parts = [part for part in tail.split("/") if part]
    if len(parts) < 2:
        raise RepositoryError("Repository must include owner and name, like github.com/owner/repo.")

    owner, repo = parts[0], parts[1]
    return GitHubRepoRef(owner=owner, repo=repo)


def clone_or_refresh_repo(repo_ref: GitHubRepoRef, repos_workspace: Path) -> Path:
    repos_workspace.mkdir(parents=True, exist_ok=True)
    repo_path = repos_workspace / repo_ref.local_key

    if not repo_path.exists():
        _run_git(["clone", "--depth", "1", repo_ref.clone_url, str(repo_path)], cwd=repos_workspace)
        return repo_path

    if not (repo_path / ".git").is_dir():
        raise RepositoryError(f"Existing path is not a git repository: {repo_path}")

    try:
        _run_git(["-C", str(repo_path), "pull", "--ff-only"], cwd=repos_workspace)
    except RepositoryError as exc:
        raise RepositoryError(
            f"Failed to refresh repository {repo_ref.slug}. "
            "Please remove the local cached copy under web/workspaces/repos and retry."
        ) from exc

    return repo_path


def _run_git(args: list[str], *, cwd: Path) -> None:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown git error"
        raise RepositoryError(detail)

