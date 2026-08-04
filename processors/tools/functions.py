import hashlib, uuid, numpy, logging, asyncio, json, time, json5, traceback, sys
from pydub import AudioSegment
from fastapi.responses import JSONResponse
import io

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

# -------------------------------- ПОлучение разницы двух текстов от 0.0 до 1.0 --
def levenstein_difference(main, correction):
    size_x = len(main) + 1
    size_y = len(correction) + 1
    matrix = numpy.zeros ((size_x, size_y))
    for x in range(size_x):
        matrix [x, 0] = x
    for y in range(size_y):
        matrix [0, y] = y

    for x in range(1, size_x):
        for y in range(1, size_y):
            if main[x-1] == correction[y-1]:
                matrix [x,y] = min(
                    matrix[x-1, y] + 1,
                    matrix[x-1, y-1],
                    matrix[x, y-1] + 1
                )
            else:
                matrix [x,y] = min(
                    matrix[x-1,y] + 1,
                    matrix[x-1,y-1] + 1,
                    matrix[x,y-1] + 1
                )

    ln = max([ len(main), len(correction) ])
    if not ln:
        return 1.0
    return int(matrix[size_x - 1, size_y - 1]) / ln


def detect_audio_format_by_content(file_data):
    if len(file_data) < 12:
        return None

    header = file_data[:12]

    if header.startswith(b'RIFF') and b'WAVE' in file_data[:20]:
        return 'wav'

    if header.startswith(b'ID3') or header.startswith(b'\xff\xfb') or header.startswith(b'\xff\xfa'):
        return 'mp3'

    if header.startswith(b'fLaC'):
        return 'flac'

    if header.startswith(b'OggS'):
        if b'OpusHead' in file_data[:100]:
            return 'ogg'

    if b'ftyp' in header:
        return 'm4a'

    if header.startswith(b'\x1a\x45\xdf\xa3'):
        return 'webm'

    return None



async def convert_audio(audio, cut_audio=True):
    try:
        maxLen = 25*1000 # 25 seconds в pydub аудиосегмент загруженный в память считается в миллисекундах
        audio_format = await asyncio.to_thread(detect_audio_format_by_content, audio)
        a = await asyncio.to_thread( lambda: AudioSegment.from_file(io.BytesIO(audio), format=audio_format).set_sample_width(2).set_frame_rate(16000) )
        if cut_audio:
            a = a[:maxLen]
        if a.channels > 1:
            a = await asyncio.to_thread(a.set_channels,1)

    except Exception as exc:
        logging.error(traceback.format_exc())
        return "WrongAudioFormat", None

    if a.duration_seconds < 0.2:
        return "AudioTooShortOrEmpty", None

    return None, a


async def put_audio_to_shm(request, audio):

    error, a = await convert_audio(audio)
    if error:
        return error, None, None

    # Зальем в оперативу сконвертированный файл
    audio_buffer = io.BytesIO()
    await asyncio.to_thread( lambda: a.export(audio_buffer, format='wav')  )
    audio_bytes = audio_buffer.read()

    # Размещаем в памяти
    size = len(audio_bytes)
    if size > (request.app.state.end - request.app.state.start):
        return "FileIsTooBig", None, None

    if request.app.state.shift + size >= request.app.state.end:
        request.app.state.shift = request.app.state.start

    start = request.app.state.shift
    end = start + size
    request.app.state.shift += end + 1

    # Размещаем в Shared
    try:
        request.app.state.shm.buf[start:end] = audio_bytes
    except Exception as exc:
        logging.error(traceback.format_exc())
        return "SharedMemoryError", None, None
    return None, start, end
