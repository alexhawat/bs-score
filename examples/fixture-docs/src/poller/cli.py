import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poller")
    parser.add_argument("--config", default="config/poller.yml")
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(f"config={args.config} once={args.once}")
