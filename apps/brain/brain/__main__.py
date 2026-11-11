"""Run the API and the worker loop in one process."""

from __future__ import annotations

import logging
import threading

import uvicorn

from brain.main import app
from brain.migrate import migrate
from brain.worker import run_worker

HOST = "0.0.0.0"
PORT = 8000


def main() -> None:
    """Apply the schema, start the worker thread, then serve HTTP.

    The schema files are idempotent and are applied before anything else, so
    code never runs against a database that lacks what it needs (on
    2026-11-11 a release went live ahead of its schema because this was a
    separate manual step). A failure stops the start-up: the previous
    container keeps serving.
    """
    logging.basicConfig(level=logging.INFO)
    migrate()
    logging.getLogger(__name__).info("cmap schema applied")
    stop = threading.Event()
    worker = threading.Thread(
        target=run_worker,
        args=(stop,),
        name="brain-worker",
        daemon=True,
    )
    worker.start()
    try:
        uvicorn.run(app, host=HOST, port=PORT)
    finally:
        stop.set()
        worker.join(timeout=5)


if __name__ == "__main__":
    main()
