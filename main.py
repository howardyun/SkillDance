from analyzer.env import load_environment
from analyzer.skills_security_matrix.cli import main as analyzer_main


def main():
    load_environment()
    return analyzer_main()


if __name__ == "__main__":
    raise SystemExit(main())
