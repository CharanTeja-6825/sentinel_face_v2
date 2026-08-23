"""RQ worker entrypoint — INIT.md §2.1, §8.7.

A 50-minute video sampled at 2 fps is 6,000 frames; even at 20 ms each that is
minutes of compute, far beyond any HTTP timeout. Video processing must run
here, with the client polling job status.

The prototype runs one worker, but this process boundary is the seam that later
allows horizontal scaling, so it is built properly now (§2.1).
"""

from __future__ import annotations

import logging

import redis
from rq import Queue, Worker

from app.config import settings
from app.services.face_engine import load_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("worker")


def main() -> None:
    settings.warn_if_unverified()

    # Load the model once in the parent process (§14.10). RQ forks per job, so
    # every job inherits it copy-on-write instead of paying the load again.
    try:
        load_engine(det_size=tuple(settings.video.det_size))
    except Exception:
        log.exception("Model failed to load; jobs will fail until this is fixed")

    connection = redis.Redis.from_url(settings.redis_url)
    queue = Queue(settings.video_queue, connection=connection)
    log.info("Listening on queue %r", settings.video_queue)
    Worker([queue], connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()
