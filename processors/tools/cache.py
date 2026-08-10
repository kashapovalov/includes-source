import asyncio
import json
import logging
import os
import pickle
from collections import OrderedDict
from os import makedirs
from os.path import join
from time import time


class CachedDict():
    def __init__(self, dir, config_path, size=5000):
        self.dir = dir
        self.alphabet = "0987654321abcdef"
        self.lock = asyncio.Lock()
        makedirs(self.dir, exist_ok=True)

        try:
            with open(config_path) as f:
                self.update = json.load(f)['cache']['update']
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            self.update = 3600

        self.size = int(size / 256)
        self.running = True
        t = time()
        self.data = {f + s: {'modified': t, 'data': OrderedDict()} for f in self.alphabet for s in self.alphabet}
        self._started = False
        self._start_lock = asyncio.Lock()

    async def _init_cache(self):
        async with self._start_lock:
            if self._started:
                return
            try:
                await self.load_from_file()
            except Exception as e:
                logging.error(f"Ошибка при загрузке кэша: {e}")
            asyncio.create_task(self._auto_save_worker())
            self._started = True

    async def add(self, key_hash, data):
        await self._init_cache()
        async with self.lock:
            prefix, key = key_hash[:2], key_hash[2:]
            self.data[prefix]['modified'] = time()
            self.data[prefix]['data'][key] = data
            if len(self.data[prefix]['data']) > self.size:
                self.data[prefix]['data'].popitem(last=False)

    async def get(self, key_hash):
        await self._init_cache()
        async with self.lock:
            prefix, key = key_hash[:2], key_hash[2:]
            data = self.data[prefix]['data']
            if key not in data:
                return None
            self.data[prefix]['modified'] = time()
            data.move_to_end(key)
            return data[key]

    async def _auto_save_worker(self):
        while self.running:
            await asyncio.sleep(self.update)
            await self.save_to_file()

    async def save_to_file(self):
        now = time()
        async with self.lock:
            saves = [(p, list(self.data[p]['data'].items())) for p in self.data if self.data[p]['modified'] >= now - self.update]
        for prefix, data_items in saves:
            try:
                await self._write_prefix_io(prefix, data_items)
            except Exception as e:
                logging.error(f"Ошибка при сохранении кэша {prefix}: {e}")

    async def load_from_file(self):
        prefixes = [f + s for f in self.alphabet for s in self.alphabet]
        loaded = await asyncio.gather(*[self._read_prefix_io(p) for p in prefixes])
        async with self.lock:
            t = time()
            for prefix, items in zip(prefixes, loaded):
                if items:
                    self.data[prefix]['data'] = OrderedDict(items)
                    self.data[prefix]['modified'] = t

    async def _read_prefix_io(self, prefix):
        return await asyncio.to_thread(self._read_prefix_file, prefix)

    async def _write_prefix_io(self, prefix, data_items):
        await asyncio.to_thread(self._write_prefix_file, prefix, data_items)

    def _read_prefix_file(self, prefix):
        path = join(self.dir, prefix)
        try:
            if os.path.exists(path):
                with open(path, 'rb') as fl:
                    return pickle.load(fl)
        except Exception:
            pass
        return []

    def _write_prefix_file(self, prefix, data_items):
        with open(join(self.dir, prefix), 'wb') as f:
            pickle.dump(data_items, f)
