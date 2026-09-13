"""The script the fixture skill actually ships (deploy.sh does not exist)."""

import argparse


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--environment', required=True)
    return parser
