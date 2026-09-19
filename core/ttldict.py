# -*- coding: utf-8 -*-
"""
core/ttldict.py
===============
Эстутумдагы сессиялар үчүн сөздүк: `ttl` секунд бою тийилбеген
жазуулар өзүнөн өзү өчөт. Тазалоо ар 5 мүнөттө бир жолу, жазуу
же окуу учурунда жүрөт — өзүнчө thread керек эмес.
"""
import threading
import time

TTLDICT_VERSION = "v2"


class TTLDict(dict):
    def __init__(self, ttl=7200, sweep_every=300):
        super().__init__()
        self._ttl = ttl
        self._sweep_every = sweep_every
        self._seen = {}
        self._last_sweep = time.time()
        self._lock = threading.Lock()

    def _touch(self, key):
        now = time.time()
        self._seen[key] = now
        if now - self._last_sweep < self._sweep_every:
            return
        with self._lock:
            self._last_sweep = now
            dead = [k for k, t in list(self._seen.items())
                    if now - t > self._ttl]
            for k in dead:
                dict.pop(self, k, None)
                self._seen.pop(k, None)
        if dead:
            print(f"[ttl] {len(dead)} эски сессия тазаланды")

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, value)
        self._touch(key)

    def __getitem__(self, key):
        value = dict.__getitem__(self, key)
        self._touch(key)
        return value

    def get(self, key, default=None):
        if dict.__contains__(self, key):
            self._touch(key)
        return dict.get(self, key, default)

    def setdefault(self, key, default=None):
        if not dict.__contains__(self, key):
            dict.__setitem__(self, key, default)
        self._touch(key)
        return dict.__getitem__(self, key)

    def pop(self, key, *default):
        self._seen.pop(key, None)
        return dict.pop(self, key, *default)
