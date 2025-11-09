"""Command-line interface for yaya."""
import sys
from . import get_version


def main():
    """Main CLI entry point."""
    if len(sys.argv) > 1 and sys.argv[1] in ('--version', '-V'):
        print(get_version())
        return 0

    print("yaya: Yet Another YAML AST transformer")
    print(f"Version: {get_version()}")
    print()
    print("Usage:")
    print("  python -m yaya --version    Show version with git hash")
    print()
    print("For programmatic use:")
    print("  from yaya import YAYA")
    print("  doc = YAYA.load('file.yaml')")
    return 0


if __name__ == '__main__':
    sys.exit(main())
