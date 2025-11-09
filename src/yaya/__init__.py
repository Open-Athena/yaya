"""
yaya: Yet Another YAML AST transformer - Byte-for-byte preserving YAML editor.
"""
from .document import YAYA

__version__ = "0.1.1"
__all__ = ["YAYA", "get_version"]


def get_version(include_git=True):
    """
    Get the version string, optionally including git commit hash.

    Args:
        include_git: If True, append git hash to version (default: True)

    Returns:
        Version string like "0.1.1" or "0.1.1+git.abc1234"

    Examples:
        >>> import yaya
        >>> yaya.get_version()
        '0.1.1+git.abc1234'
        >>> yaya.get_version(include_git=False)
        '0.1.1'
    """
    if not include_git:
        return __version__

    try:
        import subprocess
        from pathlib import Path

        # Find the repo root (where .git is)
        package_dir = Path(__file__).parent
        repo_root = package_dir.parent.parent

        # Get short hash
        result = subprocess.run(
            ['git', 'rev-parse', '--short=7', 'HEAD'],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=1
        )

        if result.returncode == 0:
            git_hash = result.stdout.strip()

            # Check if working tree is dirty
            dirty_result = subprocess.run(
                ['git', 'diff-index', '--quiet', 'HEAD', '--'],
                cwd=repo_root,
                timeout=1
            )
            dirty = '.dirty' if dirty_result.returncode != 0 else ''

            return f"{__version__}+git.{git_hash}{dirty}"
    except Exception:
        # If git is not available or any error, just return version
        pass

    return __version__
