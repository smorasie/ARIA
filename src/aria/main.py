import logging

from aria.logging_config import setup_logging


def main():
    setup_logging()

    logger = logging.getLogger("aria")
    logger.info("ARIA is running.")


if __name__ == "__main__":
    main()
