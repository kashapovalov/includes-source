import atexit
import logging
import logging.handlers
import os
import sys
import threading
import traceback
from multiprocessing import Queue

import json5

try:
    with open('config.json') as f:
        config = json5.load(f)['logs']
except Exception as e:
    logging.error(traceback.format_exc())
    sys.exit()

log_queue = Queue()
log_level = logging.getLevelName(config.get('level','INFO'))

log_path = os.path.join(config['path'], 'log.txt')
os.makedirs(config['path'], exist_ok=True)

_listener = None


class StreamToLogger:
    def __init__(self, logger_name, level, original_stream):
        self.logger = logging.getLogger(logger_name)
        self.level = level
        self.original_stream = original_stream
        self.exclude = ["^"]
        self._local = threading.local()  # Защита от рекурсии в рамках одного потока

    def write(self, buf):
        # Если этот поток уже находится внутри записи лога — пишем напрямую в оригинальный stderr
        if getattr(self._local, 'lock', False):
            self.original_stream.write(buf)
            return

        self._local.lock = True
        try:
            for line in buf.rstrip().splitlines():
                line = line.strip()
                if line and not any(ex in line for ex in self.exclude):
                    self.logger.log(self.level, line)
        finally:
            self._local.lock = False

    def flush(self):
        self.original_stream.flush()

    def isatty(self):
        return False

def setup_logging():
    global log_queue

    root_logger = logging.getLogger()

    disabled = [
        "onnx_ir",
        "torch.onnx",
        "onnxscript",
        "nemo_logging",
        "faster_whisper",
        "matplotlib",
        "python_multipart.multipart"
    ]
    for name in disabled:
        logging.getLogger(name).setLevel(log_level)

    # Avoid duplicate queue handlers in parent/child processes.
    if not any(isinstance(handler, logging.handlers.QueueHandler) and handler.queue is log_queue
               for handler in root_logger.handlers):
        root_logger.addHandler(logging.handlers.QueueHandler(log_queue))

    root_logger.setLevel(log_level)

    configure_uvicorn_logging()
    #redirect_stdio_to_logging()


def configure_uvicorn_logging():
    # Uvicorn CLI ставит свои StreamHandler'ы, которые пишут в stdout/stderr.
    # Убираем их и отдаём записи в root logger -> QueueHandler -> log.txt.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(log_level)


def redirect_stdio_to_logging():
    if not isinstance(sys.stdout, StreamToLogger):
        sys.stdout = StreamToLogger("sys.stdout", logging.INFO, sys.__stdout__)
    if not isinstance(sys.stderr, StreamToLogger):
        sys.stderr = StreamToLogger("sys.stderr", logging.ERROR, sys.__stderr__)

def start_log_listener():
    global _listener, log_queue

    # Reuse an already running listener.
    if _listener is not None and getattr(_listener, "_thread", None) is not None:
        if _listener._thread.is_alive():
            return _listener

    os.makedirs(config['path'], exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_path,
        maxBytes=config['maxSize'],
        backupCount=config['backups'],
        encoding='utf-8'
    )
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)

    _listener = logging.handlers.QueueListener(log_queue, file_handler, respect_handler_level=True)
    _listener.start()
    atexit.register(_listener.stop)

    return _listener

start_log_listener()
setup_logging()
