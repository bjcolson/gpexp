# filename : scripts.py
# created  : 06/23/2025


import logging
import sys

import click

lg = logging.getLogger(__name__)
lg.setLevel(logging.DEBUG)


@click.command()
def gpexp (  ):

    logging.basicConfig(level=logging.DEBUG)
    from gpexp.app.main import main
    main()
    


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
