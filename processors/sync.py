import json
import logging
import os
import subprocess
import time
from os.path import join

from processors.tools.globals import global_config


def worker(exchanger, name, args):

    service = args['service']
    path = args['path']

    try:
        from setproctitle import setproctitle
        setproctitle(f"{service}: {name}")
    except Exception: pass

    params = global_config['cluster']
    servers = params['nodes']

    if os.path.isfile(params['logfile']):
        os.unlink(params['logfile'])

    if os.path.isfile(params['statusFile']):
        os.unlink(params['statusFile'])

    p = subprocess.Popen(['ip','addr'], stdout=subprocess.PIPE)
    ipAddr = str(p.communicate()[0])

    for i in range(len(servers)-1,-1,-1):
        if servers[i] in ipAddr:
            del servers[i]

    if not len(servers):
        logging.info('Синхронизация серверов не требуется')
        exchanger[name]['ready'].value = True
        return None

    conf_path = join('/tmp', service, 'lsyncd.lua')
    os.makedirs(os.path.dirname(conf_path), exist_ok=True)
    with open(conf_path,'w') as conf:
        conf.write("settings {\n")
        conf.write(f'    logfile = "{params["logfile"]}",\n')
        conf.write(f'    statusFile = "{params["statusFile"]}",\n')
        conf.write("    nodaemon = true,\n")
        conf.write("    maxProcesses = 1\n")
        conf.write("}\n\n")

        for server in servers:
            conf.write("sync {\n")
            conf.write("    default.rsyncssh,\n")
            conf.write(f'    source = "{path}",\n')
            conf.write(f'    targetdir = "{path}",\n')
            conf.write(f'    host = "{server}",\n')
            conf.write("    rsync = {\n")
            conf.write("    }\n")
            conf.write("}\n\n")
        conf.close()

    # Пробуем запустить синхронизацию
    try:
        p = subprocess.Popen(['lsyncd', '-nodaemon', conf_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        time.sleep(3)
        if p.poll() is not None:
            output = (p.stdout.read() if p.stdout else b'').decode(errors='replace').strip()
            logging.error('Ошибка запуска lsyncd (код %s, конфиг %s): %s. Подробности: %s', p.returncode, conf_path, output or 'нет вывода', params['logfile'],)
            return None
    except Exception:
        logging.exception('Ошибка запуска lsyncd (конфиг %s)', conf_path)
        return None

    exchanger[name]['ready'].value = True
    while True:
        time.sleep(1.0)
