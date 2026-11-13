"""
The ORRIN app's line to the voice process: a Unix socket in $XDG_RUNTIME_DIR/orrin/ (directory
0700, socket 0600; connections from any other user are dropped via SO_PEERCRED). Not a network
listener. Quickshell (OrrinLink.qml) connects with Quickshell.Io.Socket.

JSON lines both ways. Requests {"op": …}; the server pushes events {"ev": …} to every client:
  thread, message, task, task_line, confirm, confirm_done, busy, tool, usage, state
Ops are dispatched to handlers given by orrin.py (AppBridge).
"""
import asyncio
import json
import os
import socket
import struct

from . import config as C

SOCKET = C.RUNTIME / "orrin" / "app.sock"


class AppServer:
    def __init__(self, loop, handlers, log=print, path=SOCKET):
        self.loop, self.handlers, self.log, self.path = loop, handlers, log, path
        self.clients = set()
        self.server = None

    async def start(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        old = os.umask(0o177)
        try:
            self.server = await asyncio.start_unix_server(self._client, path=str(self.path), limit=1 << 20)
        finally:
            os.umask(old)
        os.chmod(self.path, 0o600)

    def _same_user(self, writer):
        sock = writer.get_extra_info("socket")
        try:
            _pid, uid, _gid = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
        except OSError:
            return False
        return uid == os.getuid()

    async def _client(self, reader, writer):
        if not self._same_user(writer):
            writer.close()
            return
        self.clients.add(writer)
        try:
            await self._dispatch({"op": "hello"}, writer)
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if isinstance(msg, dict):
                    await self._dispatch(msg, writer)
        except (ConnectionError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        finally:
            self.clients.discard(writer)
            try:
                writer.close()
            except Exception:
                pass

    async def _dispatch(self, msg, writer):
        fn = self.handlers.get(msg.get("op"))
        if not fn:
            return
        try:
            out = await asyncio.to_thread(fn, msg)        # handlers may touch SQLite; keep the loop free
        except Exception as e:
            self.log(f"ORRIN: app {msg.get('op')}: {type(e).__name__}: {e}")
            out = {"ev": "error", "op": msg.get("op"), "error": str(e)[:200]}
        for ev in (out if isinstance(out, list) else [out] if out else []):
            await self._send(writer, ev)

    async def _send(self, writer, ev):
        try:
            writer.write((json.dumps(ev, ensure_ascii=False, default=str) + "\n").encode())
            await writer.drain()
        except Exception:
            self.clients.discard(writer)

    def broadcast(self, ev):
        """Thread-safe: push an event to every connected app."""
        def go():
            for w in list(self.clients):
                asyncio.ensure_future(self._send(w, ev))
        try:
            self.loop.call_soon_threadsafe(go)
        except RuntimeError:
            pass
