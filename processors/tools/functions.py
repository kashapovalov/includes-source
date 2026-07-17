import hashlib, uuid, numpy, logging, asyncio, json, time, json5, traceback, sys
from fastapi.responses import JSONResponse

try:
    with open('config.json') as f:
        global_config = json5.load(f)['logs']
except Exception as e:
    logging.error(traceback.format_exc())
    sys.exit()

def md5(text):
    data = text if not isinstance(text,str) else text.encode('utf-8')
    return str(hashlib.md5(data).hexdigest())

def task_id():
    return str(uuid.uuid4())

def cosine_similarity(x,y):
    try:
        return numpy.dot(x,y)/(numpy.linalg.norm(x)*numpy.linalg.norm(y))
    except:
        return 0.0

def request(exchange, request, id=None, wait_for_result=True, timeout=30, default=None):

    if not ready(exchange):
        return default

    if not id:
        id = task_id()

    exchange['requests'].put((id,request))
    if not wait_for_result:
        return id
    i=int(timeout/0.01)
    no_pause = 10
    while not id in exchange['replies'] and i:
        if no_pause:
            no_pause -= 1
            continue
        time.sleep(0.01)
        i -= 1
    if not i:
        return default

    result = exchange['replies'][id]
    if result == None:
        result = default
    del exchange['replies'][id]
    return result

async def async_request(exchange, request, id=None, wait_for_result=True, timeout=60, default=None):

    if not ready(exchange):
        return default

    if not id:
        id = task_id()

    exchange['requests'].put((id,request))
    if not wait_for_result:
        return id
    i=int(timeout/0.01)
    no_pause = 10
    while not id in exchange['replies'] and i:
        if no_pause:
            no_pause -= 1
            continue
        await asyncio.sleep(0.01)
        i -= 1
    if not i:
        return default

    result = exchange['replies'][id]
    if result == None:
        result = default
    del exchange['replies'][id]
    return result

def value(exchange,param):
    try:
        return exchange['params'][param]
    except:
        return None

def ready(exchange):
    try:
        return exchange['ready'].value
    except:
        return False

def hash(exchange):
    try:
        return exchange['hash'].value
    except:
        return False

def abort(message, code=405):
    return JSONResponse(
        status_code=code,
        content={
            "error": 1,
            "message": message
        }
    )
