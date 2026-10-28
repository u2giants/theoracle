"""Run the API and the worker loop in one process."""

from __future__ import annotations

import logging
import threading

import uvicorn

from brain.main import app
from brain.worker import run_worker

HOST = "0.0.0.0"
PORT = 8000


def main() -> None:
    """Start the worker thread, then serve HTTP until interrupted."""
    logging.basicConfig(level=logging.INFO)
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
