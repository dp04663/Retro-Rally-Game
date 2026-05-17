"""LAN multiplayer: UDP discovery, invites, host-authoritative race sync."""

import json
import socket
import struct
import threading
import time
import uuid
from queue import Queue, Empty

UDP_PORT = 45777
TCP_PORT = 45778
BEACON_MAGIC = "RETRO_RALLY_MP"
PRESENCE_TTL = 10.0
LOBBY_TTL = 8.0
INVITE_TTL = 30.0
MAX_OPPONENTS = 8


def _local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _send_udp(payload, addr=None):
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(data) > 1400:
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        if addr:
            sock.sendto(data, addr)
        else:
            sock.sendto(data, ("<broadcast>", UDP_PORT))
    except OSError:
        pass
    finally:
        sock.close()


def _tcp_send(sock, msg):
    line = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
    sock.sendall(struct.pack("!I", len(line)) + line)


def _tcp_recv_lines(sock, buf):
    while True:
        if b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if line:
                try:
                    return json.loads(line.decode("utf-8")), buf
                except json.JSONDecodeError:
                    pass
        chunk = sock.recv(4096)
        if not chunk:
            return None, buf
        buf += chunk


class MultiplayerManager:
    def __init__(self):
        self.local_ip = _local_ip()
        self.lobby_id = str(uuid.uuid4())[:8]
        self.running = False
        self.mode = None
        self.inbox = Queue()
        self._presence = {}
        self._lobbies = {}
        self._invites = []
        self._profile = {}
        self._roster = []
        self._clients = {}
        self._client_sock = None
        self._client_slot = None
        self._latest_state = None
        self._host_user = ""
        self._last_beacon = 0.0
        self._last_presence = 0.0
        self._udp_stop = threading.Event()
        self._tcp_stop = threading.Event()
        self._server_sock = None
        self._udp_thread = None
        self._server_thread = None
        self._client_thread = None
        self._lock = threading.Lock()

    def set_profile(self, user, chassis_id, color, decal_style, decal_color):
        self._profile = {
            "user": user,
            "chassis_id": int(chassis_id),
            "color": [int(color[0]), int(color[1]), int(color[2])],
            "decal_style": int(decal_style),
            "decal_color": [int(decal_color[0]), int(decal_color[1]), int(decal_color[2])],
        }

    def start_browse(self):
        self.stop()
        self.mode = "browse"
        self.running = True
        self._udp_stop.clear()
        self._udp_thread = threading.Thread(target=self._udp_listen_loop, daemon=True)
        self._udp_thread.start()

    def start_host(self):
        self.stop()
        self.mode = "host"
        self.running = True
        self.lobby_id = str(uuid.uuid4())[:8]
        self._roster = []
        self._clients = {}
        self._udp_stop.clear()
        self._tcp_stop.clear()
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(("0.0.0.0", TCP_PORT))
        self._server_sock.listen(MAX_OPPONENTS)
        self._server_sock.settimeout(0.5)
        self._udp_thread = threading.Thread(target=self._udp_listen_loop, daemon=True)
        self._server_thread = threading.Thread(target=self._host_accept_loop, daemon=True)
        self._udp_thread.start()
        self._server_thread.start()
        self.inbox.put({"type": "host_started", "lobby_id": self.lobby_id})

    def stop(self):
        self.running = False
        self._udp_stop.set()
        self._tcp_stop.set()
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None
        if self._client_sock:
            try:
                self._client_sock.close()
            except OSError:
                pass
            self._client_sock = None
        self.mode = None
        self._roster = []
        self._clients = {}
        self._client_slot = None
        self._latest_state = None

    def tick(self):
        if not self.running:
            return
        now = time.time()
        if self.mode in ("browse", "host"):
            if now - self._last_presence > 1.8 and self._profile:
                self._last_presence = now
                _send_udp(
                    {
                        "magic": BEACON_MAGIC,
                        "type": "presence",
                        "user": self._profile.get("user", ""),
                        "ip": self.local_ip,
                        "chassis_id": self._profile.get("chassis_id", 0),
                        "color": self._profile.get("color", [200, 50, 50]),
                        "status": "host" if self.mode == "host" else "idle",
                    }
                )
        if self.mode == "host" and now - self._last_beacon > 1.2:
            self._last_beacon = now
            slots_open = max(0, MAX_OPPONENTS - len(self._roster))
            _send_udp(
                {
                    "magic": BEACON_MAGIC,
                    "type": "lobby",
                    "lobby_id": self.lobby_id,
                    "host": self._profile.get("user", "host"),
                    "host_ip": self.local_ip,
                    "tcp_port": TCP_PORT,
                    "slots_open": slots_open,
                    "racers": len(self._roster) + 1,
                }
            )
        self._prune_stale(now)

    def seek_and_invite(self):
        """Notify online players (LAN) to join this host lobby."""
        if self.mode != "host":
            return 0
        sent = 0
        now = time.time()
        with self._lock:
            peers = list(self._presence.values())
        for p in peers:
            user = p.get("user", "")
            if user == self._profile.get("user"):
                continue
            if now - p.get("ts", 0) > PRESENCE_TTL:
                continue
            _send_udp(
                {
                    "magic": BEACON_MAGIC,
                    "type": "invite",
                    "lobby_id": self.lobby_id,
                    "host": self._profile.get("user", "host"),
                    "host_ip": self.local_ip,
                    "tcp_port": TCP_PORT,
                    "message": f"{self._profile.get('user', 'Someone')} invited you to a race!",
                },
                (p.get("ip", "255.255.255.255"), UDP_PORT),
            )
            sent += 1
        self.inbox.put({"type": "invites_sent", "count": sent})
        return sent

    def join_lobby(self, host_ip, tcp_port=TCP_PORT):
        if self.mode == "host":
            return False
        self.stop()
        self.mode = "client"
        self.running = True
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(6.0)
            sock.connect((host_ip, tcp_port))
            sock.settimeout(None)
            self._client_sock = sock
            hello = {"type": "hello", **self._profile}
            _tcp_send(sock, hello)
            self._tcp_stop.clear()
            self._client_thread = threading.Thread(
                target=self._client_read_loop, args=(sock,), daemon=True
            )
            self._client_thread.start()
            self._udp_stop.clear()
            self._udp_thread = threading.Thread(target=self._udp_listen_loop, daemon=True)
            self._udp_thread.start()
            self.inbox.put({"type": "join_sent", "host_ip": host_ip})
            return True
        except OSError as e:
            self.stop()
            self.inbox.put({"type": "error", "message": f"Could not join: {e}"})
            return False

    def notify_race_start(self):
        if self.mode != "host":
            return
        for c in list(self._clients.values()):
            try:
                _tcp_send(c["sock"], {"type": "race_start"})
            except OSError:
                pass

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except Empty:
                break
        return out

    def online_players(self):
        now = time.time()
        me = self._profile.get("user", "")
        with self._lock:
            rows = []
            for p in self._presence.values():
                if now - p.get("ts", 0) > PRESENCE_TTL:
                    continue
                if p.get("user") == me:
                    continue
                rows.append(dict(p))
            rows.sort(key=lambda r: r.get("user", ""))
            return rows

    def open_lobbies(self):
        now = time.time()
        with self._lock:
            rows = []
            for lb in self._lobbies.values():
                if now - lb.get("ts", 0) > LOBBY_TTL:
                    continue
                if lb.get("host_ip") == self.local_ip and self.mode == "host":
                    continue
                rows.append(dict(lb))
            rows.sort(key=lambda r: r.get("host", ""))
            return rows

    def pending_invites(self):
        now = time.time()
        with self._lock:
            return [inv for inv in self._invites if now - inv.get("ts", 0) <= INVITE_TTL]

    def roster(self):
        return list(self._roster)

    def is_host(self):
        return self.mode == "host"

    def is_client(self):
        return self.mode == "client"

    def is_active(self):
        return self.mode in ("host", "client")

    def client_slot(self):
        return self._client_slot

    def latest_state(self):
        return self._latest_state

    def send_input(self, throttle, brake, steer):
        if self.mode != "client" or not self._client_sock:
            return
        try:
            _tcp_send(
                self._client_sock,
                {
                    "type": "input",
                    "throttle": float(throttle),
                    "brake": float(brake),
                    "steer": float(steer),
                },
            )
        except OSError:
            pass

    def broadcast_state(self, player_car, bots):
        if self.mode != "host":
            return
        cars = [
            {
                "x": player_car["x"],
                "y": player_car["y"],
                "angle": player_car["angle"],
                "vx": player_car["vx"],
                "vy": player_car["vy"],
                "lap": player_car.get("lap", 0),
                "color": list(player_car.get("color", (220, 50, 50))),
                "chassis_id": player_car.get("chassis_id", 0),
                "decal_style": player_car.get("decal_style", 0),
                "decal_color": list(player_car.get("decal_color", [255, 255, 255])),
                "is_player": True,
            }
        ]
        for b in bots:
            cars.append(
                {
                    "x": b["x"],
                    "y": b["y"],
                    "angle": b["angle"],
                    "vx": b["vel_x"],
                    "vy": b["vel_y"],
                    "lap": b.get("lap", 0),
                    "color": list(b.get("color", (180, 180, 180))),
                    "chassis_id": b.get("chassis_id", 0),
                    "decal_style": b.get("decal_style", 0),
                    "decal_color": list(b.get("decal_color", [255, 255, 255])),
                    "control": b.get("control", "ai"),
                    "user": b.get("remote_user", ""),
                    "is_player": False,
                }
            )
        msg = {"type": "state", "cars": cars, "t": time.time()}
        dead = []
        for cid, c in list(self._clients.items()):
            try:
                _tcp_send(c["sock"], msg)
            except OSError:
                dead.append(cid)
        for cid in dead:
            self._drop_client(cid)

    def apply_roster_to_bots(self, bots):
        """Replace AI slots with connected human racers (host side)."""
        for i, bot in enumerate(bots):
            bot["control"] = "ai"
            bot.pop("remote_input", None)
            bot.pop("remote_user", None)
            bot.pop("chassis_id", None)
        for entry in self._roster:
            slot = entry.get("slot")
            if slot is None or slot < 0 or slot >= len(bots):
                continue
            b = bots[slot]
            b["control"] = "remote"
            b["remote_user"] = entry.get("user", "Racer")
            b["chassis_id"] = entry.get("chassis_id", 0)
            b["color"] = tuple(entry.get("color", (200, 200, 200)))
            b["decal_style"] = entry.get("decal_style", 0)
            b["decal_color"] = tuple(entry.get("decal_color", (255, 255, 255)))
            b["remote_input"] = {"throttle": 0.0, "brake": 0.0, "steer": 0.0}

    def apply_state_as_client(self, state, local_slot):
        """Returns dict for host player car + mutates view of bots list data."""
        if not state:
            return None
        cars = state.get("cars", [])
        host_car = None
        opponents = []
        for i, c in enumerate(cars):
            if c.get("is_player"):
                host_car = c
            else:
                opponents.append(c)
        return {"host_car": host_car, "opponents": opponents, "slot": local_slot}

    def _prune_stale(self, now):
        with self._lock:
            for k in list(self._presence.keys()):
                if now - self._presence[k].get("ts", 0) > PRESENCE_TTL:
                    del self._presence[k]
            for k in list(self._lobbies.keys()):
                if now - self._lobbies[k].get("ts", 0) > LOBBY_TTL:
                    del self._lobbies[k]
            self._invites = [inv for inv in self._invites if now - inv.get("ts", 0) <= INVITE_TTL]

    def _udp_listen_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", UDP_PORT))
        except OSError:
            return
        sock.settimeout(0.4)
        while not self._udp_stop.is_set():
            try:
                data, addr = sock.recvfrom(2048)
                payload = json.loads(data.decode("utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            if payload.get("magic") != BEACON_MAGIC:
                continue
            payload["ip"] = addr[0]
            payload["ts"] = time.time()
            ptype = payload.get("type")
            with self._lock:
                if ptype == "presence":
                    key = payload.get("user", addr[0])
                    self._presence[key] = payload
                elif ptype == "lobby":
                    self._lobbies[payload.get("lobby_id", addr[0])] = payload
                elif ptype == "invite" and self.mode in ("browse", "client"):
                    self._invites.insert(0, payload)
                    self.inbox.put({"type": "invite", **payload})
        sock.close()

    def _host_accept_loop(self):
        while not self._tcp_stop.is_set():
            try:
                conn, addr = self._server_sock.accept()
            except (OSError, socket.timeout):
                continue
            threading.Thread(
                target=self._host_client_loop, args=(conn, addr), daemon=True
            ).start()

    def _assign_slot(self):
        used = {r["slot"] for r in self._roster}
        for s in range(MAX_OPPONENTS):
            if s not in used:
                return s
        return None

    def _host_client_loop(self, conn, addr):
        cid = str(uuid.uuid4())[:8]
        buf = b""
        try:
            while not self._tcp_stop.is_set():
                while len(buf) < 4:
                    chunk = conn.recv(4096)
                    if not chunk:
                        raise ConnectionError("closed")
                    buf += chunk
                (n,) = struct.unpack("!I", buf[:4])
                buf = buf[4:]
                while len(buf) < n:
                    chunk = conn.recv(4096)
                    if not chunk:
                        raise ConnectionError("closed")
                    buf += chunk
                line = buf[:n]
                buf = buf[n:]
                if not line.endswith(b"\n"):
                    continue
                msg = json.loads(line.decode("utf-8"))
                mtype = msg.get("type")
                if mtype == "hello":
                    slot = self._assign_slot()
                    if slot is None:
                        _tcp_send(conn, {"type": "reject", "reason": "Race is full"})
                        conn.close()
                        return
                    entry = {
                        "client_id": cid,
                        "slot": slot,
                        "user": msg.get("user", "Racer"),
                        "chassis_id": msg.get("chassis_id", 0),
                        "color": msg.get("color", [200, 200, 200]),
                        "decal_style": msg.get("decal_style", 0),
                        "decal_color": msg.get("decal_color", [255, 255, 255]),
                    }
                    with self._lock:
                        self._clients[cid] = {"sock": conn, "addr": addr, "entry": entry}
                        self._roster.append(entry)
                    _tcp_send(conn, {"type": "welcome", "slot": slot, "lobby_id": self.lobby_id})
                    self.inbox.put({"type": "player_joined", **entry})
                elif mtype == "input":
                    slot = None
                    with self._lock:
                        if cid in self._clients:
                            slot = self._clients[cid]["entry"]["slot"]
                    if slot is not None:
                        self.inbox.put(
                            {
                                "type": "remote_input",
                                "slot": slot,
                                "throttle": msg.get("throttle", 0.0),
                                "brake": msg.get("brake", 0.0),
                                "steer": msg.get("steer", 0.0),
                            }
                        )
        except (OSError, ConnectionError, json.JSONDecodeError):
            pass
        finally:
            self._drop_client(cid)
            try:
                conn.close()
            except OSError:
                pass

    def _drop_client(self, cid):
        with self._lock:
            self._clients.pop(cid, None)
            self._roster = [r for r in self._roster if r.get("client_id") != cid]
        self.inbox.put({"type": "player_left", "client_id": cid})

    def _client_read_loop(self, sock):
        buf = b""
        try:
            while not self._tcp_stop.is_set():
                while len(buf) < 4:
                    chunk = sock.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                (n,) = struct.unpack("!I", buf[:4])
                buf = buf[4:]
                while len(buf) < n:
                    chunk = sock.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                line = buf[:n]
                buf = buf[n:]
                if not line.endswith(b"\n"):
                    continue
                msg = json.loads(line.decode("utf-8"))
                mtype = msg.get("type")
                if mtype == "welcome":
                    self._client_slot = msg.get("slot")
                    self.inbox.put({"type": "joined", "slot": self._client_slot})
                elif mtype == "reject":
                    self.inbox.put({"type": "error", "message": msg.get("reason", "Rejected")})
                    self.stop()
                elif mtype == "state":
                    self._latest_state = msg
                elif mtype == "race_start":
                    self.inbox.put({"type": "race_start"})
        except (OSError, json.JSONDecodeError):
            self.inbox.put({"type": "error", "message": "Disconnected from host"})
            self.stop()
