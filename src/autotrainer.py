"""Autonomous UCN training, bounded to the exact game process, with LAN viewer."""

from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlsplit, parse_qs
import argparse
import io
import ipaddress
import json
import logging
import secrets
import socket
import threading
import time
import webbrowser

import numpy as np

from connectome import Brain, ROOT
from autopolicy import Learner
from screen_reader import ScreenReader
from defense_knowledge import DefenseAdvisor, catalog
from game_audio import GameAudio, FEATURE_COUNT, combine


class ExclusiveHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        # Windows SO_REUSEADDR may otherwise allow a second,
        # unrelated server to bind the same port.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_EXCLUSIVEADDRUSE,
                1,
            )

        super().server_bind()


class EpisodeLoop:
    """Autonomous UCN episode state machine."""

    def __init__(
        self,
        game,
        learner,
        brain,
        log,
    ):
        self.game = game
        self.learner = learner
        self.brain = brain
        self.log = log

        self.phase = "menu"
        self.active = False
        self.verified = False

        self.elapsed = 0.0
        self.started = 0.0
        self.last_progress = 0.0

        self.deadline = 0.0

        self.last_scene = ""
        self.stable = 0

        self.last_known = time.monotonic()
        self.last_recovery = 0.0

        self.results = deque(
            maxlen=80
        )

        self.action = "WAIT"
        self.note = "Oczekiwanie na menu UCN"
        self.advisor = DefenseAdvisor()

    def abort(
        self,
        reason,
    ):
        if self.active:
            self.learner.finish(
                "abort",
                self.elapsed,
            )

            self.log(
                "abort",
                reason=reason,
                seconds=self.elapsed,
            )

        self.active = False
        self.verified = False
        self.phase = "menu"

        self.note = reason

        self.game.release()
        self.advisor.reset()

    def observe(
        self,
        obs,
        now,
        features=None,
        captured_at=None,
    ):
        captured_at = now if captured_at is None else captured_at
        self.advisor.observe(obs, captured_at)
        if obs.scene == self.last_scene:
            self.stable += 1
        else:
            self.stable = 1

        self.last_scene = obs.scene

        if obs.scene != "unknown":
            self.last_known = now

        if now < self.deadline:
            return

        if obs.scene == "menu":
            if self.active:
                self.abort(
                    "Powrót do menu bez rozpoznanego wyniku; "
                    "próba pominięta"
                )

            if (
                self.phase == "verify"
                and obs.verified50
            ):
                self.verified = True

                if (
                    "go" in obs.buttons
                    and self.game.click_normalized(
                        *obs.buttons["go"]
                    )
                ):
                    self.phase = "starting"
                    self.deadline = now + 1.5

                    self.note = (
                        "Potwierdzone 50/20. "
                        "Uruchamiam noc."
                    )

                    self.log(
                        "configured",
                        difficulty="50/20",
                        evidence=obs.texts,
                    )

            elif (
                self.phase != "verify"
                or now - self.last_recovery > 5
            ):
                if (
                    "twenty" in obs.buttons
                    and self.game.click_normalized(
                        *obs.buttons["twenty"]
                    )
                ):
                    self.phase = "verify"
                    self.last_recovery = now
                    self.deadline = now + 0.5

                    self.note = (
                        "Ustawiam wszystkie postacie na 20 "
                        "i sprawdzam punktację."
                    )

            else:
                self.note = (
                    "Sprawdzam 50/20. "
                    "Brak potwierdzenia 10 000 punktów — "
                    "nie uruchamiam innej trudności."
                )

        elif (
            obs.scene == "instructions"
            and self.verified
        ):
            if (
                "go" in obs.buttons
                and self.game.click_normalized(
                    *obs.buttons["go"]
                )
            ):
                self.phase = "starting"
                self.deadline = now + 1.0

        elif obs.scene in ("playing", "interruption"):
            if not self.active:
                if not self.verified:
                    self.note = (
                        "Zastana noc bez potwierdzonego 50/20. "
                        "Wracam do menu."
                    )

                    self.game.perform(
                        "ESC"
                    )

                    self.deadline = now + 2
                    return

                self.active = True
                self.phase = "playing"

                self.elapsed = 0.0
                self.started = now
                self.last_progress = now

                self.brain.reset()
                self.advisor.reset()
                self.advisor.observe(obs, captured_at)

                if hasattr(
                    self.learner,
                    "reset_memory",
                ):
                    self.learner.reset_memory()

                self.log(
                    "start",
                    difficulty="50/20",
                    episode=(
                        self.learner.episodes
                        + 1
                    ),
                )

            if obs.seconds is not None:
                delta = (
                    obs.seconds
                    - self.elapsed
                )

                # Reject OCR jumps. Wall-clock waiting
                # never counts as survival reward.
                maximum_delta = max(
                    5.0,
                    (
                        now
                        - self.last_progress
                    )
                    * 1.5
                    + 2,
                )

                if (
                    0
                    <= delta
                    <= maximum_delta
                    and obs.seconds <= 400
                ):
                    self.learner.progress(
                        delta,
                        through=captured_at,
                        next_features=features,
                    )

                    self.elapsed = (
                        obs.seconds
                    )

                    if delta > 0:
                        self.last_progress = (
                            now
                        )

            self.note = (
                f"Trening 50/20 · "
                f"noc {self.learner.episodes + 1} · "
                f"{self.elapsed:.1f} s"
            )

        elif (
            obs.scene in (
                "loss",
                "win",
            )
            and self.stable >= 2
        ):
            if self.active:
                result = {
                    "episode": (
                        self.learner.episodes
                        + 1
                    ),
                    "result": obs.scene,
                    "seconds": round(
                        self.elapsed,
                        1,
                    ),
                }

                self.learner.finish(
                    obs.scene,
                    self.elapsed,
                )

                self.results.append(
                    result
                )

                self.log(
                    "result",
                    **result,
                    updates=self.learner.updates,
                )

                self.active = False
                self.verified = False
                self.phase = "result"

                self.note = (
                    "Wynik zapisany. "
                    "Model zaktualizowany. "
                    "Uruchamiam następną próbę."
                )

                self.deadline = now + 2
                return

            # Result screens are UI, not gameplay actions.
            self.game.click_normalized(
                *obs.buttons.get(
                    "continue",
                    (
                        0.5,
                        0.8,
                    ),
                )
            )

            self.phase = "menu"
            self.deadline = now + 2

        elif (
            obs.scene == "bonus"
            and self.stable >= 2
        ):
            if self.active:
                self.abort(
                    "Ekran przedmiotu bez pewnego wyniku — "
                    "próba pominięta"
                )

            self.game.click_normalized(
                0.5,
                0.5,
            )

            self.deadline = now + 2

        elif obs.scene == "unknown":
            self.note = (
                "Przejście / nierozpoznany ekran — "
                "sprawdzam wynik."
            )

            if (
                now - self.last_known > 20
                and now - self.last_recovery > 20
            ):
                self.abort(
                    "Przekroczony czas rozpoznawania; "
                    "automatyczny powrót do menu"
                )

                self.game.perform(
                    "ESC"
                )

                self.last_recovery = now
                self.deadline = now + 2

        if (
            self.active
            and now - self.started > 420
        ):
            self.abort(
                "Limit długości nocy; wynik niepotwierdzony"
            )

            self.game.perform(
                "ESC"
            )

            self.deadline = now + 2

    def act(
        self,
        features,
        now,
    ):
        if not self.active:
            return

        if now < self.deadline:
            return

        if self.last_scene in (
            "menu",
            "instructions",
            "win",
            "loss",
            "bonus",
        ):
            return

        if (
            now
            - self.last_known
            > 3
        ):
            return

        advice = self.advisor.suggest(now)
        if advice:
            action, mouse, transition = self.learner.guided(features, advice.action, advice.mouse)
        else:
            action, mouse, transition = self.learner.act(features)

        if self.game.perform(
            action,
            mouse,
        ):
            self.action = action
            self.advisor.performed(action, now, advice)

            self.learner.record(
                transition,
                at=now,
            )


class Trainer:
    def __init__(
        self,
    ):
        from windows_game import Game, GAME_EXE

        self.lock = threading.RLock()
        self.closed = threading.Event()

        self.paused = False

        self.commands = deque()
        self.events = deque(
            maxlen=30
        )

        self.brain = Brain()

        self.learner = Learner(
            self.brain.meta[
                "feature_count"
            ] + FEATURE_COUNT,
            self.brain.meta[
                "signature"
            ],
            ROOT
            / "models"
            / "auto50_policy.npz",
            extra_features=FEATURE_COUNT,
        )
        self.audio = GameAudio(GAME_EXE)

        self.game = Game(
            self.command,
            global_resume=True,
        )

        self.loop = EpisodeLoop(
            self.game,
            self.learner,
            self.brain,
            self.log,
        )

        journal = (
            ROOT
            / "logs"
            / "auto50.jsonl"
        )

        if journal.exists():
            with journal.open(
                encoding="utf-8"
            ) as f:
                for line in deque(
                    f,
                    maxlen=500,
                ):
                    try:
                        item = json.loads(
                            line
                        )

                        if (
                            item.get("event")
                            == "result"
                        ):
                            self.loop.results.append(
                                item
                            )

                    except ValueError:
                        continue

        self.reader = None
        self.latest = None
        self.observed = None

        self.ocr_id = 0
        self.used_id = 0

        self.jpeg = b""

        self.frame_time = 0.0
        self.ticks = 0
        self.fps = 0.0

        self.focused = False

        self.error = ""
        self.ocr_text = []

        self.anatomy = (
            self.brain.anatomy()
        )

        self.view_activity = []
        self.feature_frames = deque(maxlen=64)

        self.worker = threading.Thread(
            target=self.run,
            daemon=True,
            name="autotrainer",
        )

        self.ocr_worker = threading.Thread(
            target=self.read_loop,
            daemon=True,
            name="screen-reader",
        )

    def log(
        self,
        kind,
        **data,
    ):
        item = {
            "time": time.strftime(
                "%H:%M:%S"
            ),
            "event": kind,
            **data,
        }

        self.events.appendleft(
            item
        )

        journal = (
            ROOT
            / "logs"
            / "auto50.jsonl"
        )

        with journal.open(
            "a",
            encoding="utf-8",
        ) as f:
            f.write(
                json.dumps(
                    item,
                    ensure_ascii=False,
                )
                + "\n"
            )

        logging.info(
            "%s",
            item,
        )

    def command(
        self,
        name,
    ):
        if name == "play":
            name = "start"
        if name in (
            "stop",
            "pause",
            "shutdown",
        ):
            self.game.emergency.set()
            self.game.release()

        if name == "shutdown":
            self.closed.set()

        if name in (
            "stop",
            "pause",
            "start",
            "save",
            "shutdown",
        ):
            with self.lock:
                self.commands.append(
                    name
                )

    def read_loop(
        self,
    ):
        try:
            self.reader = (
                ScreenReader()
            )

            while not self.closed.is_set():
                with self.lock:
                    current = (
                        self.latest
                    )

                if (
                    current is None
                    or self.paused
                ):
                    self.closed.wait(
                        0.2
                    )

                    continue

                frame, stamp = (
                    current
                )

                obs = (
                    self.reader.read(
                        frame
                    )
                )

                with self.lock:
                    self.observed = (
                        obs,
                        stamp,
                    )

                    self.ocr_id += 1

                self.closed.wait(
                    0.12
                )

        except Exception as exc:
            logging.exception(
                "OCR failed"
            )

            self.error = (
                "OCR: "
                + str(exc)
            )

            self.command(
                "stop"
            )

    def run(
        self,
    ):
        try:
            self.game.launch()

            if not self.game.wait_for_window(
                60
            ):
                raise RuntimeError(
                    "Nie znaleziono okna UCN"
                )

            self.game.activate(
                10
            )

            self.ocr_worker.start()

            last_save = (
                time.monotonic()
            )

            last_action = 0.0

            lost_at = None

            last_launch = (
                last_save
            )

            while not self.closed.is_set():
                begin = (
                    time.monotonic()
                )

                with self.lock:
                    while self.commands:
                        cmd = (
                            self.commands.popleft()
                        )

                        if cmd in (
                            "pause",
                            "stop",
                            "shutdown",
                        ):
                            self.paused = True

                            self.loop.abort(
                                "Zatrzymano. "
                                "F7 w grze wznawia trening."
                            )

                            self.learner.save()

                            if cmd == "shutdown":
                                self.closed.set()

                        elif cmd == "start":
                            self.paused = False
                            self.error = ""

                            self.game.emergency.clear()
                            self.note = "F7 odebrane — uruchamiam UCN."
                            self.loop.note = self.note
                            self.log("resume", source="F7 / panel")
                            self.latest = None
                            self.observed = None
                            self.feature_frames.clear()
                            if not self.game.find(force=True):
                                self.game.launch()
                                self.game.wait_for_window(20)

                            self.loop.last_known = (
                                begin
                            )

                            self.loop.deadline = (
                                begin
                                + 0.3
                            )

                            activated = self.game.activate(
                                5
                            )
                            if not activated:
                                self.loop.note = "F7 odebrane. Kliknij okno UCN — Windows nie przyznał mu fokusu."

                        elif cmd == "save":
                            self.learner.save()

                self.focused = (
                    self.game.focused()
                )

                if self.game.emergency.is_set():
                    self.paused = True

                if (
                    self.paused
                    or not self.focused
                ):
                    if lost_at is None:
                        lost_at = begin

                    if (
                        self.loop.active
                        and begin
                        - lost_at
                        > 1
                    ):
                        self.loop.abort(
                            "Utrata aktywnego okna; "
                            "próba pominięta"
                        )

                    with self.lock:
                        self.latest = None
                        self.observed = None
                        self.feature_frames.clear()

                        self.used_id = (
                            self.ocr_id
                        )

                    if (
                        not self.paused
                        and not self.game.find()
                        and begin
                        - last_launch
                        > 30
                    ):
                        self.game.launch()

                        last_launch = (
                            begin
                        )

                        if self.game.wait_for_window(
                            20
                        ):
                            self.game.activate(
                                5
                            )

                    self.closed.wait(
                        0.1
                    )

                    continue

                lost_at = None

                frame = (
                    self.game.capture()
                )

                if frame is None:
                    continue

                with self.lock:
                    self.latest = (
                        frame,
                        begin,
                    )

                self.audio.update(self.game.process_id())
                audio_features, _ = self.audio.sample()
                x = combine(self.brain.step(frame), audio_features)
                self.feature_frames.append((begin, x.copy()))

                with self.lock:
                    observed = (
                        self.observed
                    )

                    oid = (
                        self.ocr_id
                    )

                if (
                    observed
                    and oid
                    != self.used_id
                    and begin
                    - observed[1]
                    < 4
                ):
                    obs, stamp = (
                        observed
                    )

                    self.ocr_text = (
                        obs.texts
                    )

                    self.loop.observe(
                        obs,
                        begin,
                        features=next((v for t,v in reversed(self.feature_frames) if t==stamp), None),
                        captured_at=stamp,
                    )

                    self.used_id = (
                        oid
                    )

                # Never let stale OCR dismiss a fresh
                # death transition.
                brightness = np.asarray(
                    frame
                    .convert("L")
                    .resize(
                        (
                            96,
                            54,
                        )
                    )
                )

                near_black = (
                    float(
                        np.mean(
                            brightness
                            > 28
                        )
                    )
                    < 0.10
                )

                if (
                    begin
                    - last_action
                    >= 0.22
                    and (not near_black or self.loop.advisor.suggest(begin) is not None)
                ):
                    self.loop.act(
                        x,
                        begin,
                    )

                    last_action = (
                        begin
                    )

                small = (
                    frame.copy()
                )

                small.thumbnail(
                    (
                        960,
                        540,
                    )
                )

                buf = io.BytesIO()

                small.save(
                    buf,
                    "JPEG",
                    quality=72,
                )

                with self.lock:
                    self.jpeg = (
                        buf.getvalue()
                    )

                    self.frame_time = (
                        time.time()
                    )

                    self.ticks += 1

                    self.view_activity = (
                        self.brain.activity()
                    )

                    self.fps = (
                        1
                        / max(
                            0.001,
                            (
                                time.monotonic()
                                - begin
                            ),
                        )
                    )

                if (
                    begin
                    - last_save
                    > 30
                ):
                    self.learner.save()

                    last_save = (
                        begin
                    )

                self.closed.wait(
                    max(
                        0,
                        (
                            0.16
                            - (
                                time.monotonic()
                                - begin
                            )
                        ),
                    )
                )

        except Exception as exc:
            logging.exception(
                "Training failed"
            )

            self.error = (
                str(exc)
            )

            self.paused = True

        finally:
            self.game.release()
            self.learner.save()

    def state(
        self,
    ):
        with self.lock:
            return {
                "application":
                    "fly-ucn-autotrainer",

                "paused":
                    self.paused,

                "focused":
                    self.focused,

                "phase":
                    self.loop.phase,

                "note":
                    self.error
                    or self.loop.note,

                "action":
                    self.loop.action,

                "seconds":
                    self.loop.elapsed,

                "episodes":
                    self.learner.episodes,

                "wins":
                    self.learner.wins,

                "best":
                    self.learner.best,

                "updates":
                    self.learner.updates,
                "continuous_updates": self.learner.continuous_updates,
                "audio": self.audio.sample()[1],
                "guided_steps": self.learner.guided_steps,
                "pending_steps": len(self.learner.pending),
                "defense_reason": self.loop.advisor.last_reason,

                "steps":
                    self.learner.steps,

                "loss":
                    self.learner.loss,

                "entropy":
                    self.learner.entropy,

                "fps":
                    round(
                        min(
                            self.fps,
                            6.25,
                        ),
                        1,
                    ),

                "activity":
                    self.view_activity,

                "ticks":
                    self.ticks,

                "frame_time":
                    self.frame_time,

                "history":
                    list(
                        self.events
                    ),

                "results":
                    list(
                        self.loop.results
                    ),

                "ocr":
                    self.ocr_text,

                "verified50":
                    self.loop.verified,

                "ocr_ready":
                    self.reader
                    is not None,
            }

    def close(
        self,
    ):
        self.closed.set()

        self.game.close()

        self.worker.join(
            timeout=10
        )
        self.audio.close()

        if not self.worker.is_alive():
            self.learner.save()


def usable_ipv4(
    value,
):
    try:
        address = ipaddress.ip_address(
            value
        )

    except ValueError:
        return False

    if address.version != 4:
        return False

    if address.is_unspecified:
        return False

    if address.is_multicast:
        return False

    return True


def local_addresses(
    include_loopback=True,
):
    """
    Discover IPv4 addresses that can actually be used
    by another device on the LAN.

    getaddrinfo(hostname) alone is unreliable on Windows,
    especially with Wi-Fi + Ethernet + VPN adapters.
    """

    ips = set()

    if include_loopback:
        ips.add(
            "127.0.0.1"
        )

    hostnames = {
        socket.gethostname(),
        socket.getfqdn(),
    }

    for hostname in hostnames:
        try:
            for info in socket.getaddrinfo(
                hostname,
                None,
                socket.AF_INET,
                socket.SOCK_STREAM,
            ):
                ip = (
                    info[4][0]
                )

                if usable_ipv4(
                    ip
                ):
                    ips.add(
                        ip
                    )

        except OSError:
            pass

        try:
            _name, _aliases, found = (
                socket.gethostbyname_ex(
                    hostname
                )
            )

            for ip in found:
                if usable_ipv4(
                    ip
                ):
                    ips.add(
                        ip
                    )

        except OSError:
            pass

    # Determine the IPv4 address Windows would use
    # for a normal outbound route.
    #
    # UDP connect() here does not establish a TCP
    # connection and sends no application data.
    for target in (
        (
            "8.8.8.8",
            53,
        ),
        (
            "1.1.1.1",
            53,
        ),
    ):
        sock = None

        try:
            sock = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM,
            )

            sock.settimeout(
                0.25
            )

            sock.connect(
                target
            )

            ip = (
                sock.getsockname()[0]
            )

            if usable_ipv4(
                ip
            ):
                ips.add(
                    ip
                )

        except OSError:
            pass

        finally:
            if sock is not None:
                sock.close()

    return {
        ip
        for ip in ips
        if not ip.startswith(
            "169.254."
        )
    }


def is_lan_ip(
    value,
):
    try:
        ip = ipaddress.ip_address(
            value
        )

    except ValueError:
        return False

    if ip.version != 4:
        return False

    if ip.is_loopback:
        return True

    if ip.is_private:
        return True

    # Some Windows/VPN configurations use
    # non-global address ranges which are still
    # reachable only locally.
    return not (
        ip.is_global
        or ip.is_multicast
        or ip.is_unspecified
    )


def host_header_parts(
    raw,
):
    if not raw:
        return (
            "",
            None,
        )

    raw = raw.strip()

    if ":" not in raw:
        return (
            raw,
            None,
        )

    host, port_text = (
        raw.rsplit(
            ":",
            1,
        )
    )

    try:
        return (
            host,
            int(port_text),
        )

    except ValueError:
        return (
            "",
            None,
        )


def make_handler(
    trainer,
    token,
    viewer,
    addresses,
    port,
):
    allowed_names = {
        "localhost",
        socket.gethostname().lower(),
        socket.getfqdn().lower(),
    }

    class Handler(
        BaseHTTPRequestHandler
    ):
        def setup(
            self,
        ):
            super().setup()

            self.connection.settimeout(
                5
            )

        def log_message(
            self,
            *args,
        ):
            pass

        def send(
            self,
            body,
            kind="application/json",
            status=200,
            headers=None,
        ):
            self.send_response(
                status
            )

            self.send_header(
                "Content-Type",
                kind,
            )

            self.send_header(
                "Content-Length",
                str(
                    len(body)
                ),
            )

            self.send_header(
                "Cache-Control",
                "no-store",
            )

            self.send_header(
                "X-Content-Type-Options",
                "nosniff",
            )

            self.send_header(
                "Referrer-Policy",
                "no-referrer",
            )

            for key, value in (
                headers
                or {}
            ).items():
                self.send_header(
                    key,
                    value,
                )

            self.end_headers()

            try:
                self.wfile.write(
                    body
                )

            except (
                BrokenPipeError,
                ConnectionResetError,
                ConnectionAbortedError,
            ):
                pass

        def client_is_lan(
            self,
        ):
            return is_lan_ip(
                self.client_address[0]
            )

        def local(
            self,
        ):
            return (
                self.client_address[0]
                == "127.0.0.1"
            )

        def valid_host(
            self,
        ):
            host, supplied_port = (
                host_header_parts(
                    self.headers.get(
                        "Host",
                        "",
                    )
                )
            )

            if supplied_port not in (
                None,
                port,
            ):
                return False

            host_lower = (
                host.lower()
            )

            if host_lower in allowed_names:
                return True

            if host in addresses:
                return True

            # Do not reject a legitimate Wi-Fi address
            # just because hostname resolution failed to
            # enumerate that Windows adapter.
            return is_lan_ip(
                host
            )

        def authorized(
            self,
        ):
            if not self.valid_host():
                return False

            if not self.client_is_lan():
                return False

            if self.local():
                return True

            cookie = SimpleCookie()

            try:
                cookie.load(
                    self.headers.get(
                        "Cookie",
                        "",
                    )
                )

            except Exception:
                return False

            return (
                "fly_view" in cookie
                and secrets.compare_digest(
                    cookie[
                        "fly_view"
                    ].value,
                    viewer,
                )
            )

        def do_GET(
            self,
        ):
            parsed = urlsplit(
                self.path
            )

            supplied = (
                parse_qs(
                    parsed.query
                )
                .get(
                    "view",
                    [""],
                )[0]
            )

            if (
                self.valid_host()
                and self.client_is_lan()
                and supplied
                and secrets.compare_digest(
                    supplied,
                    viewer,
                )
            ):
                self.send(
                    b"",
                    status=303,
                    headers={
                        "Location": "/",
                        "Set-Cookie": (
                            f"fly_view={viewer}; "
                            "HttpOnly; "
                            "SameSite=Strict; "
                            "Path=/"
                        ),
                    },
                )

                return

            if not self.authorized():
                self.send(
                    (
                        b"Open the phone link generated "
                        b"by FnafFly on the PC."
                    ),
                    kind="text/plain; charset=utf-8",
                    status=403,
                )

                return

            path = (
                parsed.path
            )

            if path == "/api/state":
                data = (
                    trainer.state()
                )

                if self.local():
                    data[
                        "phone_urls"
                    ] = [
                        (
                            f"http://"
                            f"{address}:"
                            f"{port}/"
                            f"?view={viewer}"
                        )
                        for address
                        in sorted(
                            addresses
                        )
                        if address
                        != "127.0.0.1"
                    ]

                    data[
                        "lan_addresses"
                    ] = sorted(
                        address
                        for address
                        in addresses
                        if address
                        != "127.0.0.1"
                    )

                self.send(
                    json.dumps(
                        data,
                        ensure_ascii=False,
                    ).encode()
                )

                return

            if path == "/api/anatomy":
                self.send(
                    json.dumps(
                        trainer.anatomy
                    ).encode()
                )

                return

            if path == "/api/knowledge":
                self.send(json.dumps(catalog(), ensure_ascii=False).encode())
                return

            if path == "/api/frame":
                self.send(
                    trainer.jpeg,
                    "image/jpeg",
                )

                return

            files = {
                "/":
                    "auto.html",

                "/auto.js":
                    "auto.js",

                "/auto.css":
                    "auto.css",
            }

            if path not in files:
                self.send(
                    b"Not found",
                    kind="text/plain; charset=utf-8",
                    status=404,
                )

                return

            file = (
                ROOT
                / "ui"
                / files[path]
            )

            content = (
                file.read_text(
                    encoding="utf-8"
                )
                .replace(
                    "__TOKEN__",
                    (
                        token
                        if self.local()
                        else ""
                    ),
                )
                .replace(
                    "__CONTROL__",
                    (
                        "true"
                        if self.local()
                        else "false"
                    ),
                )
            )

            if path == "/":
                kind = (
                    "text/html; charset=utf-8"
                )

            elif path.endswith(
                ".js"
            ):
                kind = (
                    "text/javascript; charset=utf-8"
                )

            else:
                kind = (
                    "text/css; charset=utf-8"
                )

            self.send(
                content.encode(),
                kind,
            )

        def do_POST(
            self,
        ):
            try:
                length = int(
                    self.headers.get(
                        "Content-Length",
                        "0",
                    )
                )

                if not (
                    0
                    < length
                    < 1024
                ):
                    raise ValueError()

                body = (
                    self.rfile.read(
                        length
                    )
                )

            except (
                ValueError,
                TimeoutError,
                OSError,
            ):
                self.send(
                    b"Invalid request",
                    kind="text/plain; charset=utf-8",
                    status=400,
                )

                return

            origin = (
                self.headers.get(
                    "Origin"
                )
            )

            expected_origin = (
                "http://"
                + self.headers.get(
                    "Host",
                    "",
                )
            )

            if (
                not self.local()
                or not self.valid_host()
                or self.path
                != "/api/command"
                or not secrets.compare_digest(
                    self.headers.get(
                        "X-Fly-Token",
                        "",
                    ),
                    token,
                )
                or (
                    origin
                    and origin
                    != expected_origin
                )
            ):
                self.send(
                    b"Forbidden",
                    kind="text/plain; charset=utf-8",
                    status=403,
                )

                return

            try:
                payload = (
                    json.loads(
                        body
                    )
                )

                cmd = (
                    payload.get(
                        "command"
                    )
                )

                if cmd not in (
                    "start",
                    "stop",
                    "pause",
                    "save",
                    "shutdown",
                ):
                    raise ValueError()

                trainer.command(
                    cmd
                )

                self.send(
                    b'{"ok":true}'
                )

            except (
                ValueError,
                TypeError,
                AttributeError,
            ):
                self.send(
                    b"Invalid command",
                    kind="text/plain; charset=utf-8",
                    status=400,
                )

    return Handler


def main(
    ):
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--port",
        type=int,
        default=8766,
    )

    parser.add_argument(
        "--no-browser",
        action="store_true",
    )

    args = parser.parse_args()

    (
        ROOT
        / "logs"
    ).mkdir(
        exist_ok=True
    )

    logging.basicConfig(
        filename=(
            ROOT
            / "logs"
            / "autotrainer.log"
        ),
        level=logging.INFO,
        encoding="utf-8",
        format="%(asctime)s %(message)s",
    )

    # Reserve the port before allocating a huge brain.
    try:
        server = ExclusiveHTTPServer(
            (
                "0.0.0.0",
                args.port,
            ),
            BaseHTTPRequestHandler,
        )

    except OSError:
        print(
            (
                f"Port {args.port} jest zajęty.\n"
                f"Panel lokalny: "
                f"http://127.0.0.1:{args.port}"
            ),
            flush=True,
        )

        return

    addresses = (
        local_addresses()
    )

    viewer_path = (
        ROOT
        / "data"
        / "cache"
        / "phone_token.txt"
    )

    viewer_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if viewer_path.exists():
        viewer = (
            viewer_path
            .read_text(
                encoding="utf-8"
            )
            .strip()
        )

    else:
        viewer = (
            secrets.token_urlsafe(
                24
            )
        )

    if not viewer:
        viewer = (
            secrets.token_urlsafe(
                24
            )
        )

    viewer_path.write_text(
        viewer,
        encoding="utf-8",
    )

    token = (
        secrets.token_urlsafe(
            32
        )
    )

    trainer = Trainer()

    # F7 resumes autonomous training.
    original = (
        trainer.game.command
    )

    trainer.game.command = (
        lambda command:
        original(
            "start"
            if command == "play"
            else command
        )
    )

    server.RequestHandlerClass = (
        make_handler(
            trainer,
            token,
            viewer,
            addresses,
            args.port,
        )
    )

    local_url = (
        f"http://127.0.0.1:"
        f"{args.port}"
    )

    phone_urls = [
        (
            f"http://"
            f"{address}:"
            f"{args.port}/"
            f"?view={viewer}"
        )
        for address
        in sorted(
            addresses
        )
        if address
        != "127.0.0.1"
    ]

    (
        ROOT
        / "PHONE_LINK.txt"
    ).write_text(
        "\n".join(
            phone_urls
        ),
        encoding="utf-8",
    )

    print()
    print(
        "========================================"
    )

    print(
        " FLY / UCN AUTOTRENER"
    )

    print(
        "========================================"
    )

    print()

    print(
        "Panel na komputerze:"
    )

    print(
        local_url
    )

    print()

    if phone_urls:
        print(
            "Podglad na telefonie:"
        )

        for url in phone_urls:
            print(
                url
            )

    else:
        print(
            "Nie wykryto adresu LAN."
        )

        print(
            "Sprawdz ipconfig i adres IPv4 karty Wi-Fi."
        )

    print()

    print(
        "Linki zapisano w PHONE_LINK.txt"
    )

    print(
        "Telefon musi byc w tej samej sieci Wi-Fi."
    )

    print()

    if not args.no_browser:
        webbrowser.open(
            local_url
        )

    trainer.worker.start()

    server.timeout = 0.5

    try:
        while not trainer.closed.is_set():
            server.handle_request()

    except KeyboardInterrupt:
        pass

    finally:
        trainer.close()
        server.server_close()


if __name__ == "__main__":
    main()
