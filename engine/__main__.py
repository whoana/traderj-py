"""Engine package entry point: python -m engine"""

import asyncio

from engine.bootstrap import bootstrap_and_run
from shared.logging_config import setup_logging

setup_logging()


def main() -> None:
    asyncio.run(bootstrap_and_run())


main()
