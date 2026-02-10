# filename : main.py
# created  : 06/23/2025


import logging
import os
import sys
from pathlib import Path

lg = logging.getLogger(__name__)
lg.setLevel(logging.DEBUG)


def main():
    lg.debug("gpexp v1 ")

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
