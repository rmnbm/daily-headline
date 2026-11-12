"""Command-line entry point, used by the daily GitHub Actions workflow.

python -m app.cli run
"""

import argparse
import logging
import sys

from app.config import MissingSettingsError, configure_logging, get_settings
from app.pipeline import Pipeline, StepFailedError

logger = logging.getLogger("app.cli")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Daily Headline NFT")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="Run the full pipeline once and publish on-chain.")
    parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        pipeline = Pipeline.from_settings(settings)
        draft, publication = pipeline.run()
    except (MissingSettingsError, StepFailedError) as exc:
        logger.error("Daily update failed: %s", exc)
        return 1

    logger.info(
        "Published %r for %s: %s (tx %s)",
        draft.headline,
        draft.date,
        publication.metadata_uri,
        publication.tx_hash,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
