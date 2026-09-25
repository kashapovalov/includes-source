import logging, traceback, time, os

def worker(exchanger, name):
    exchange = exchanger[name]
    exchange['ready'].value = True
    handles = {}

    while True:
        id, task = exchange['requests'].get()
        path = task['path']
        for i in range(3):
            try:
                if path not in handles:
                    handles[path] = open(path, 'ab')
                f = handles[path]

                text = task['text']
                if not text.endswith("\n"):
                    text += "\n"
                os.write(f.fileno(), text.encode('utf-8'))
                break
            except Exception:
                logging.error( traceback.format_exc() )
                if path in handles:
                    try:
                        handles[path].close()
                    except Exception:
                        pass
                    del handles[path]
