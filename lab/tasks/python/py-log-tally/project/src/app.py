import sys
from tally import tally

def run(argv, stdin):
    if len(argv) != 1 or not argv[0].isascii() or not argv[0].isdigit():
        raise ValueError("usage: LIMIT")
    return tally(stdin, int(argv[0]))
