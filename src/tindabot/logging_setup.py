import json
import logging
import time


class SafeFormatter(logging.Formatter):
    def format(self, record):
        # Only static event codes and allowlisted numeric metadata enter production logs.
        payload = {
            "time": time.time(),
            "level": record.levelname,
            "event": record.msg if record.name == "tindabot" else record.name,
        }
        for key in ("job_id", "error_code"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(SafeFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    for name in ("httpx", "httpcore", "google.auth", "urllib3", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)
