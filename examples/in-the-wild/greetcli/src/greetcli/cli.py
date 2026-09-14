import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="greet")
    parser.add_argument("--name", default="world")
    args = parser.parse_args()
    print(f"hello, {args.name}")
