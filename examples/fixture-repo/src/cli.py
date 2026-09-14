"""The toy CLI. Note which subcommands actually exist."""

import argparse


def build_parser():
    parser = argparse.ArgumentParser(prog='demo')
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('serve')
    sub.add_parser('migrate')
    return parser
