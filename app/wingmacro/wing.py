"""WING native protocol client: TCP 2222, channel 2 (audio engine).

Verified against a WING Rack (fw 3.1.1), 2026-10-07:
- Paths are navigated by node *name* tokens from root (numbers too: "ch", "1", "fdr").
- A data request (0xdc) is answered with `d7 <hash> <value> de`; a missing node gives a bare `de`.
- Every client gets change events (`d7 <hash> <value>`) for everything, without subscribing,
  but not for its own writes.
- The console refuses a new connection for ~1 s after the previous one; retry.
- Faders store the float as sent (no 0.1 dB rounding). -89.5 dB is the lowest level; below
  that (and -90) the value becomes -144 = -inf.
"""
import asyncio
import logging
import socket
import struct
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

PORT = 2222
ESC = 0xDF
CH_AUDIO = 1  # ChID 1 = "channel 2", audio engine & control requests

# Node types, from the definition flags (bits 4..7)
T_NODE, T_LINF, T_LOGF, T_FADER, T_INT, T_ENUM, T_FENUM, T_STR = range(8)
UNITS = ["", "dB", "%", "ms", "Hz", "m", "s", "oct"]


def discover(timeout=1.5, host="255.255.255.255"):
    """Send WING? over UDP; return a list of {ip, name, model, serial, firmware}."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(timeout)
    found = []
    try:
        s.sendto(b"WING?", (host, PORT))
        while True:
            data, _ = s.recvfrom(512)
            parts = data.decode(errors="replace").split(",")
            if parts[0] == "WING" and len(parts) >= 6:
                found.append(dict(zip(["ip", "name", "model", "serial", "firmware"], parts[1:6])))
    except OSError:
        pass
    finally:
        s.close()
    return found


# --- encoding -------------------------------------------------------------

def _name_token(seg):
    b = seg.encode()
    if not 1 <= len(b) <= 16:
        raise ValueError(f"bad path segment {seg!r}")
    return bytes([0xC0 + len(b) - 1]) + b


def nav(path):
    """Tokens that select `path` (e.g. /ch/1/fdr) starting from the root."""
    return bytes([0xDA]) + b"".join(_name_token(s) for s in path.strip("/").split("/"))


def encode_value(v):
    if isinstance(v, bool):
        return bytes([int(v)])
    if isinstance(v, int):
        if 0 <= v <= 0x3F:
            return bytes([v])
        if -0x8000 <= v < 0x8000:
            return b"\xd3" + struct.pack(">h", v)
        return b"\xd4" + struct.pack(">i", v)
    if isinstance(v, float):
        return b"\xd5" + struct.pack(">f", v)
    if isinstance(v, str):
        b = v.encode()
        if not b:
            return b"\xd0"
        if len(b) <= 64:
            return bytes([0x80 + len(b) - 1]) + b
        return bytes([0xD1, len(b) - 1]) + b[:256]
    raise TypeError(f"can't encode {v!r}")


def escape(payload):
    """Escape literal 0xdf bytes (df -> df de) so they can't be read as channel switches."""
    return payload.replace(b"\xdf", b"\xdf\xde")


# --- decoding -------------------------------------------------------------

class Unescaper:
    """Byte-level receive decoder (per the protocol doc's sample routine). Yields channel-1 bytes."""

    def __init__(self):
        self.esc = False
        self.ch = -1

    def feed(self, data):
        out = bytearray()
        for b in data:
            if b == ESC and not self.esc:
                self.esc = True
                continue
            if self.esc:
                self.esc = False
                if b != ESC:
                    if b == ESC - 1:
                        b = ESC
                    elif 0xD0 <= b < 0xD0 + 14:
                        self.ch = b - 0xD0
                        continue
                    elif self.ch == CH_AUDIO:
                        out.append(ESC)
            if self.ch == CH_AUDIO:
                out.append(b)
        return bytes(out)


@dataclass
class NodeDef:
    name: str
    longname: str
    hash: int
    type: int
    unit: str
    readonly: bool
    min: float = None
    max: float = None
    steps: int = None
    items: list = field(default_factory=list)  # enum: [str]; fenum: [float]

    @property
    def type_name(self):
        return ["node", "linf", "logf", "fader", "int", "enum", "fenum", "str"][self.type]


def parse_def(d):
    parent, h, idx = struct.unpack(">IIH", d[:10])
    j = 10
    n = d[j]; name = d[j + 1:j + 1 + n].decode(errors="replace"); j += 1 + n
    n = d[j]; longname = d[j + 1:j + 1 + n].decode(errors="replace"); j += 1 + n
    flags = struct.unpack(">H", d[j:j + 2])[0]; j += 2
    t = (flags >> 4) & 15
    nd = NodeDef(name, longname, h, t, UNITS[flags & 15] if flags & 15 < len(UNITS) else "",
                 bool(flags & 0x200))
    rest = d[j:]
    if t in (T_LINF, T_LOGF) and len(rest) >= 12:
        nd.min, nd.max, nd.steps = struct.unpack(">ffi", rest[:12])
    elif t == T_INT and len(rest) >= 8:
        nd.min, nd.max = struct.unpack(">ii", rest[:8])
    elif t in (T_ENUM, T_FENUM) and len(rest) >= 2:
        count = struct.unpack(">H", rest[:2])[0]; k = 2
        for _ in range(count):
            if t == T_ENUM:
                n = rest[k]; nd.items.append(rest[k + 1:k + 1 + n].decode(errors="replace")); k += 1 + n
            else:
                nd.items.append(struct.unpack(">f", rest[k:k + 4])[0]); k += 4
            k += 1 + rest[k]  # long item name
    return nd


class TokenParser:
    """Turns the unescaped channel-1 byte stream into ('val', hash, v) / ('end',) / ('def', NodeDef)."""

    def __init__(self):
        self.buf = bytearray()
        self.hash = None

    def feed(self, data):
        self.buf += data
        out = []
        b = self.buf
        i = 0
        while i < len(b):
            t = b[i]
            need = 1
            item = None
            if t <= 0x3F:
                item = ("val", t)
            elif t <= 0x7F or 0xD8 <= t <= 0xDD and t not in (0xD9,):
                pass  # node index / nav / requests: not expected inbound, skip
            elif t <= 0xBF:
                need = 1 + t - 0x7F
                if len(b) - i >= need:
                    item = ("val", b[i + 1:i + need].decode(errors="replace"))
            elif t <= 0xCF:
                need = 1 + t - 0xBF
            elif t == 0xD0:
                item = ("val", "")
            elif t == 0xD1:
                if len(b) - i >= 2:
                    need = 2 + b[i + 1] + 1
                    if len(b) - i >= need:
                        item = ("val", b[i + 2:i + need].decode(errors="replace"))
                else:
                    need = 2
            elif t in (0xD2, 0xD3):
                need = 3
                if t == 0xD3 and len(b) - i >= need:
                    item = ("val", struct.unpack(">h", b[i + 1:i + 3])[0])
            elif t in (0xD4, 0xD5, 0xD6, 0xD7):
                need = 5
                if len(b) - i >= need:
                    raw = bytes(b[i + 1:i + 5])
                    if t == 0xD4:
                        item = ("val", struct.unpack(">i", raw)[0])
                    elif t in (0xD5, 0xD6):
                        item = ("val", struct.unpack(">f", raw)[0])
                    else:
                        self.hash = struct.unpack(">I", raw)[0]
            elif t == 0xD9:
                need = 2
            elif t == 0xDE:
                item = ("end",)
            elif t == ESC:  # node definition response: len.w [len.l]
                if len(b) - i < 3:
                    break
                n = struct.unpack(">H", b[i + 1:i + 3])[0]
                hdr = 3
                if n == 0:
                    if len(b) - i < 7:
                        break
                    n = struct.unpack(">I", b[i + 3:i + 7])[0]
                    hdr = 7
                need = hdr + n
                if len(b) - i >= need:
                    try:
                        item = ("def", parse_def(bytes(b[i + hdr:i + need])))
                    except (IndexError, struct.error, UnicodeError):
                        log.warning("bad node definition")
            if len(b) - i < need:
                break
            i += need
            if item and item[0] == "val":
                out.append(("val", self.hash, item[1]))
                self.hash = None
            elif item:
                out.append(item)
        del b[:i]
        return out


# --- client ---------------------------------------------------------------

class Wing:
    """Async client. Keeps a value cache by path and calls listeners on changes."""

    KEEPALIVE = 5.0

    def __init__(self, host=None):
        self.host = host
        self.info = {}
        self.connected = False
        self.listeners = []  # fn(path, value)
        self.values = {}  # path -> value
        self.hash_path = {}  # hash -> path
        self.path_hash = {}  # path -> hash
        self.watched = set()
        self._writer = None
        self._pending = []  # [(kind, future)]
        self._last_val = None
        self._defs = []
        self._lock = asyncio.Lock()
        self._conn_event = asyncio.Event()
        self.on_connect = []  # async fn()

    # public API

    async def get(self, path, timeout=1.0):
        """Read a value from the console; None if the node doesn't exist."""
        r = await self._request("get", nav(path) + b"\xdc", timeout)
        if r is None:
            return None
        h, v = r
        if h is not None:
            self.hash_path[h] = path
            self.path_hash[path] = h
        self.values[path] = v
        return v

    async def defs(self, path, timeout=2.0):
        """Definitions of the children of `path` (e.g. all params of /fx/3)."""
        return await self._request("defs", nav(path) + b"\xdd", timeout) or []

    async def set(self, path, value):
        if not self.connected:
            return False
        h = self.path_hash.get(path)
        head = b"\xd7" + struct.pack(">I", h) if h is not None else nav(path)
        self._send(head + encode_value(value))
        self._changed(path, value)
        return True

    def cached(self, path, default=None):
        return self.values.get(path, default)

    async def value(self, path):
        """Cached value, fetching it (and so learning its hash for events) if unknown."""
        if path in self.values:
            return self.values[path]
        self.watched.add(path)
        return await self.get(path) if self.connected else None

    async def watch(self, paths):
        new = [p for p in paths if p not in self.watched]
        self.watched.update(paths)
        if self.connected:
            for p in new:
                await self.get(p)

    async def refresh(self):
        for p in list(self.watched):
            await self.get(p)

    async def wait_connected(self):
        await self._conn_event.wait()

    async def run(self):
        """Connect, reconnect forever."""
        delay = 1.0
        while True:
            if not self.host:
                found = await asyncio.get_running_loop().run_in_executor(None, discover)
                if found:
                    self.host = found[0]["ip"]
                    self.info = found[0]
                    log.info("discovered WING %s at %s", found[0]["name"], self.host)
                else:
                    await asyncio.sleep(3)
                    continue
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, PORT), 3)
            except (OSError, asyncio.TimeoutError) as e:
                log.debug("connect %s: %s", self.host, e)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 10)
                continue
            delay = 1.0
            await self._session(reader, writer)

    # internals

    async def _session(self, reader, writer):
        self._writer = writer
        self._ch_tx = None
        unesc, parser = Unescaper(), TokenParser()
        rx = asyncio.create_task(self._rx(reader, unesc, parser))
        try:
            self.connected = True
            self._conn_event.set()
            log.info("connected to WING at %s", self.host)
            if not self.info:
                found = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: discover(1.0, self.host))
                self.info = found[0] if found else {"ip": self.host}
            for p in list(self.watched):
                await self.get(p)
            for cb in self.on_connect:
                await cb()
            while not rx.done():
                await asyncio.wait([rx], timeout=self.KEEPALIVE)
                if not rx.done() and await self.get("/ch/1/name", 3) is None and not rx.done():
                    log.warning("WING keepalive failed")
                    break
        except (OSError, ConnectionError) as e:
            log.warning("WING session error: %s", e)
        finally:
            self.connected = False
            self._conn_event.clear()
            rx.cancel()
            writer.close()
            for _, fut in self._pending:
                if not fut.done():
                    fut.set_result(None)
            self._pending.clear()
            log.info("disconnected from WING")

    def _send(self, payload):
        if self._ch_tx != CH_AUDIO:
            self._writer.write(bytes([ESC, 0xD0 + CH_AUDIO]))
            self._ch_tx = CH_AUDIO
        self._writer.write(escape(payload))

    async def _request(self, kind, payload, timeout):
        if not self.connected:
            return None
        async with self._lock:  # one request in flight: responses are matched by order
            fut = asyncio.get_running_loop().create_future()
            self._pending.append((kind, fut))
            self._last_val, self._defs = None, []
            self._send(payload)
            try:
                return await asyncio.wait_for(fut, timeout)
            except asyncio.TimeoutError:
                if (kind, fut) in self._pending:
                    self._pending.remove((kind, fut))
                return None

    async def _rx(self, reader, unesc, parser):
        while True:
            data = await reader.read(65536)
            if not data:
                return
            for item in parser.feed(unesc.feed(data)):
                if item[0] == "val":
                    _, h, v = item
                    self._last_val = (h, v)
                    path = self.hash_path.get(h)
                    if path is not None and self.values.get(path) != v:
                        self._changed(path, v)
                elif item[0] == "def":
                    self._defs.append(item[1])
                elif item[0] == "end" and self._pending:
                    kind, fut = self._pending.pop(0)
                    if not fut.done():
                        fut.set_result(self._last_val if kind == "get" else self._defs)
                    self._last_val, self._defs = None, []

    def _changed(self, path, value):
        self.values[path] = value
        for cb in self.listeners:
            try:
                cb(path, value)
            except Exception:
                log.exception("listener failed")
