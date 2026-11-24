"""Command-line entry point.

python -m app.cli run     # full pipeline, no review (used by the daily workflow)
python -m app.cli serve   # HTTP API to prepare, review and publish drafts
"""

import argparse
import logging
import sys

from app.config import MissingSettingsError, Settings, configure_logging, get_settings
from app.pipeline import Pipeline, StepFailedError

logger = logging.getLogger("app.cli")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Daily Headline NFT")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="Run the full pipeline once and publish on-chain.")
    serve = commands.add_parser("serve", help="Start the review API.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)
    if args.command == "serve":
        return serve_api(settings, args.host, args.port)
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


def serve_api(settings: Settings, host: str, port: int) -> int:
    import uvicorn

    from app.api import create_app

    if settings.missing("api_key"):
        logger.warning("API_KEY is not set: every endpoint except /health will answer 503")
    uvicorn.run(create_app(settings), host=host, port=port, log_level=settings.log_level.lower())
    return 0


if __name__ == "__main__":
    sys.exit(main())
