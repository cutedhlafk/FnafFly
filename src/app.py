"""Loopback-only live experiment. Run using START_FLY.bat."""

from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import io
import json
import logging
import queue
import secrets
import threading
import time
import urllib.request
import webbrowser

import numpy as np
from PIL import Image

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auto50 import Auto50Bootstrap
from connectome import Brain, ROOT
from policy import Policy, ACTIONS


class Experiment:
    def __init__(
        self,
        offline=False,
        auto50=False,
    ):
        self.brain = Brain()

        self.policy = Policy(
            self.brain.meta[
                "feature_count"
            ],
            self.brain.meta[
                "signature"
            ],
        )

        self.commands = queue.Queue()
        self.lock = threading.Lock()
        self.closed = threading.Event()

        self.mode = "pause"

        self.note = (
            "Gotowy. Otwórz noc w UCN, "
            "potem F6: pokazuj grę."
        )

        self.history = deque(
            maxlen=40
        )

        self.frame = None
        self.jpeg = b""
        self.previous_x = None

        self.probabilities = (
            np.zeros(
                len(ACTIONS)
            )
        )

        self.action = "WAIT"

        self.fps = 0.0
        self.ticks = 0
        self.frame_time = 0.0
        self.focused = False

        self.episode_start = None
        self.episode_count = 0
        self.wins = 0

        self.last_save = (
            time.monotonic()
        )

        self.armed = False
        self.offline = offline
        self.game = None

        self.allow_mouse = False

        self.auto50_enabled = bool(
            auto50
            and not offline
        )

        self.auto50_status = (
            "disabled"
            if not self.auto50_enabled
            else "waiting"
        )

        self.auto50_setup_difference = 0.0
        self.auto50_go_difference = 0.0

        self.auto50 = None

        self.templates = {}

        self.template_path = (
            ROOT
            / "data"
            / "cache"
            / "terminals.npz"
        )

        if self.template_path.exists():
            with np.load(
                self.template_path,
                allow_pickle=False,
            ) as f:
                self.templates = {
                    name: f[name].copy()
                    for name in f.files
                }

        if not offline:
            from windows_game import Game

            self.game = Game(
                lambda cmd:
                self.commands.put(
                    {
                        "command": cmd
                    }
                )
            )

            if self.auto50_enabled:
                self.auto50 = (
                    Auto50Bootstrap(
                        self.game
                    )
                )

        self.anatomy = (
            self.brain.anatomy()
        )

        self.worker = (
            threading.Thread(
                target=self.run,
                name="fly-brain",
                daemon=True,
            )
        )

    def log(
        self,
        msg,
    ):
        self.note = msg

        self.history.appendleft(
            {
                "time": (
                    time.strftime(
                        "%H:%M:%S"
                    )
                ),
                "message": msg,
            }
        )

        logging.info(
            msg
        )

    def pause(
        self,
        msg,
    ):
        self.mode = "pause"
        self.previous_x = None

        if self.game:
            self.game.observe_inputs = (
                False
            )

            self.game.release()
            self.game.consume()

        self.log(
            msg
        )

    def command(
        self,
        data,
    ):
        cmd = data.get(
            "command"
        )

        if cmd in [
            "pause",
            "stop",
        ]:
            self.pause(
                (
                    "Zatrzymano. "
                    "Żaden klawisz nie jest "
                    "przytrzymany."
                )
            )

            self.policy.save()

        elif cmd in [
            "watch",
            "teach",
            "play",
            "explore",
        ]:
            if (
                self.offline
                and cmd != "watch"
            ):
                self.log(
                    (
                        "Test syntetyczny "
                        "obsługuje tylko "
                        "obserwację; dane "
                        "testowe nie służą "
                        "do uczenia gry."
                    )
                )

                return

            if (
                cmd == "play"
                and not self.policy.ready
            ):
                self.log(
                    (
                        "Za mało przykładów: "
                        "minimum 200 próbek, "
                        "w tym 30 akcji. "
                        "Najpierw F6 "
                        "i demonstracja."
                    )
                )

                return

            self.mode = cmd
            self.previous_x = None
            self.armed = False

            self.brain.reset()

            self.policy.trajectory.clear()

            if cmd in [
                "teach",
                "play",
                "explore",
            ]:
                self.brain.stimulation = (
                    None
                )

            if self.game:
                self.game.emergency.clear()

                self.game.consume()

                self.game.observe_inputs = (
                    cmd == "teach"
                )

            self.episode_start = (
                time.monotonic()
            )

            self.log(
                {
                    "watch": (
                        "Obserwacja obrazu "
                        "i aktywności neuronów."
                    ),
                    "teach": (
                        "Nauka z Twoich "
                        "klawiszy w UCN. "
                        "F8 kończy zapis."
                    ),
                    "play": (
                        "Model steruje grą, "
                        "gdy UCN ma fokus. "
                        "F12 zatrzymuje."
                    ),
                    "explore": (
                        "Eksperymentalny "
                        "trening z nagrodą: "
                        "F9 dobrze, F10 źle, "
                        "F11 wygrana. "
                        "F12 stop."
                    ),
                }[cmd]
            )

        elif cmd in [
            "positive",
            "negative",
            "win",
            "loss",
        ]:
            value = {
                "positive": 1.0,
                "negative": -1.0,
                "win": 5.0,
                "loss": -5.0,
            }[cmd]

            n = self.policy.reward(
                value
            )

            self.log(
                (
                    f"Nagroda {value:+g}; "
                    f"zaktualizowano {n} "
                    "ostatnich decyzji "
                    "modelu."
                )
            )

            if cmd in [
                "win",
                "loss",
            ]:
                self.episode_count += 1

                self.wins += int(
                    cmd == "win"
                )

                self.pause(
                    (
                        "Koniec próby "
                        "oznaczony przez "
                        "użytkownika. "
                        "Ustaw kolejną noc."
                    )
                )

                self.policy.save()

        elif cmd == "save":
            self.policy.save()

            self.log(
                (
                    "Zapisano model "
                    "i przykłady w "
                    "models/fly_policy.npz."
                )
            )

        elif cmd == "fit":
            for _ in range(
                100
            ):
                self.policy.train_batch()

            self.policy.save()

            self.log(
                (
                    "Wykonano 100 "
                    "dodatkowych aktualizacji "
                    "na zapisanych "
                    "demonstracjach."
                )
            )

        elif cmd == "mouse":
            self.allow_mouse = bool(
                data.get(
                    "enabled"
                )
            )

            self.log(
                (
                    "Sterowanie myszą "
                    "modelu: "
                    + (
                        "włączone."
                        if self.allow_mouse
                        else "wyłączone."
                    )
                )
            )

        elif cmd == "stimulate":
            if self.mode in [
                "play",
                "explore",
                "teach",
            ]:
                self.log(
                    (
                        "Stymulacja jest "
                        "dostępna tylko "
                        "w obserwacji "
                        "lub pauzie."
                    )
                )

                return

            group = data.get(
                "group"
            )

            self.brain.stimulation = (
                None
                if group is None
                else np.flatnonzero(
                    self.brain.groups
                    == int(group)
                )
            )

            self.log(
                (
                    "Zmieniono "
                    "eksperymentalną "
                    "stymulację obszaru."
                )
            )

        elif cmd == "template":
            name = data.get(
                "kind"
            )

            if (
                name
                not in [
                    "menu",
                    "win",
                    "loss",
                ]
                or self.frame is None
                or (
                    time.time()
                    - self.frame_time
                    > 5
                )
            ):
                self.log(
                    (
                        "Wzorzec wymaga "
                        "świeżego obrazu UCN "
                        "(ostatnie 5 sekund)."
                    )
                )

                return

            self.templates[
                name
            ] = (
                np.asarray(
                    self.frame
                    .convert("L")
                    .resize(
                        (
                            64,
                            36,
                        )
                    ),
                    np.float32,
                )
                / 255
            )

            self.template_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            np.savez_compressed(
                self.template_path,
                **self.templates,
            )

            self.pause(
                (
                    "Zapisano wzorzec "
                    + name
                    + ". Podobny ekran "
                    "automatycznie zatrzyma "
                    "sterowanie."
                )
            )

        else:
            raise ValueError(
                "Unknown command"
            )

    def run_auto50_bootstrap(
        self
    ):
        if (
            not self.auto50_enabled
            or not self.auto50
        ):
            return

        self.auto50_status = (
            "starting"
        )

        self.log(
            (
                "AUTO50: uruchamiam UCN "
                "i przygotowuję 50/20. "
                "F12 natychmiast przerywa "
                "automatyzację."
            )
        )

        result = (
            self.auto50.run()
        )

        self.auto50_setup_difference = (
            result.setup_difference
        )

        self.auto50_go_difference = (
            result.go_difference
        )

        if not result.ok:
            self.auto50_status = (
                "failed"
            )

            self.pause(
                (
                    "AUTO50 zatrzymane: "
                    + result.message
                )
            )

            return

        self.auto50_status = (
            "night_started"
        )

        self.mode = "watch"
        self.previous_x = None
        self.armed = False

        self.brain.reset()

        self.policy.trajectory.clear()

        self.episode_start = (
            time.monotonic()
        )

        if self.game:
            self.game.consume()

            self.game.observe_inputs = (
                False
            )

        self.log(
            (
                "AUTO50: "
                + result.message
                + " Na tym etapie model "
                "tylko obserwuje; "
                "sterowanie i RL dołączymy "
                "w kolejnym kroku."
            )
        )

    def run(self):
        if self.auto50_enabled:
            try:
                self.run_auto50_bootstrap()

            except Exception:
                logging.exception(
                    (
                        "AUTO50 bootstrap "
                        "failed"
                    )
                )

                self.auto50_status = (
                    "failed"
                )

                self.pause(
                    (
                        "AUTO50 zakończyło się "
                        "błędem. Szczegóły są "
                        "w logs/app.log."
                    )
                )

        while not self.closed.is_set():
            started = (
                time.monotonic()
            )

            try:
                while True:
                    try:
                        data = (
                            self.commands
                            .get_nowait()
                        )

                    except queue.Empty:
                        break

                    with self.lock:
                        self.command(
                            data
                        )

                if self.mode == "pause":
                    self.closed.wait(
                        0.08
                    )

                    continue

                if self.offline:
                    frame = (
                        Image.fromarray(
                            np.tile(
                                np.arange(
                                    256,
                                    dtype=np.uint8,
                                ),
                                (
                                    144,
                                    1,
                                ),
                            )
                        )
                    )

                    self.focused = True

                else:
                    frame = (
                        self.game.capture()
                    )

                    self.focused = (
                        self.game.focused()
                    )

                if frame is None:
                    if (
                        self.mode
                        in [
                            "play",
                            "explore",
                        ]
                        and (
                            self.armed
                            or (
                                self.episode_start
                                and (
                                    time.monotonic()
                                    - self.episode_start
                                    > 15
                                )
                            )
                        )
                    ):
                        with self.lock:
                            self.pause(
                                (
                                    "UCN utraciło fokus. "
                                    "Sterowanie "
                                    "zatrzymane; "
                                    "F7 w grze wznowi "
                                    "model."
                                )
                            )

                    if self.game:
                        self.game.consume()

                    self.previous_x = None

                    self.closed.wait(
                        0.15
                    )

                    continue

                with self.lock:
                    self.frame = frame

                    self.frame_time = (
                        time.time()
                    )

                    self.armed = True

                if self.mode in [
                    "play",
                    "explore",
                ]:
                    small = (
                        np.asarray(
                            frame
                            .convert("L")
                            .resize(
                                (
                                    64,
                                    36,
                                )
                            ),
                            np.float32,
                        )
                        / 255
                    )

                    matched = next(
                        (
                            name
                            for (
                                name,
                                ref,
                            ) in (
                                self.templates
                                .items()
                            )
                            if (
                                np.abs(
                                    small
                                    - ref
                                ).mean()
                                < 0.045
                            )
                        ),
                        None,
                    )

                    if matched:
                        with self.lock:
                            if (
                                matched
                                != "menu"
                            ):
                                self.command(
                                    {
                                        "command":
                                        matched
                                    }
                                )

                            self.pause(
                                (
                                    "Rozpoznano "
                                    "zapisany ekran: "
                                    + matched
                                    + "."
                                )
                            )

                        continue

                events = (
                    self.game.consume()
                    if self.game
                    else []
                )

                x = self.brain.step(
                    frame
                )

                with self.lock:
                    if (
                        self.mode
                        == "teach"
                        and self.previous_x
                        is not None
                    ):
                        if events:
                            # Label the state BEFORE
                            # the captured action,
                            # not its resulting frame.
                            for (
                                name,
                                mouse,
                            ) in events:
                                self.policy.remember(
                                    self.previous_x,
                                    ACTIONS.index(
                                        name
                                    ),
                                    mouse,
                                )

                        elif (
                            self.ticks
                            % 3
                            == 0
                        ):
                            self.policy.remember(
                                self.previous_x,
                                0,
                                (
                                    self.game.cursor()
                                    if self.game
                                    else (
                                        0.5,
                                        0.5,
                                    )
                                ),
                            )

                        for _ in range(
                            2
                        ):
                            self.policy.train_batch()

                    (
                        action,
                        p,
                        mouse,
                    ) = self.policy.predict(
                        x,
                        explore=(
                            self.mode
                            == "explore"
                        ),
                    )

                    if not self.allow_mouse:
                        p[
                            ACTIONS.index(
                                "CLICK"
                            )
                        ] = 0

                        p[
                            ACTIONS.index(
                                "MOVE"
                            )
                        ] = 0

                    # Renormalize the actual
                    # executed policy, including
                    # its action mask.
                    p = p / p.sum()

                    action = (
                        int(
                            self.policy.rng.choice(
                                len(p),
                                p=p,
                            )
                        )
                        if (
                            self.mode
                            == "explore"
                        )
                        else int(
                            p.argmax()
                        )
                    )

                    self.probabilities = p

                    self.action = (
                        ACTIONS[
                            action
                        ]
                    )

                    self.previous_x = x

                    mode = self.mode

                if (
                    mode
                    in [
                        "play",
                        "explore",
                    ]
                    and self.game
                ):
                    if self.game.perform(
                        ACTIONS[
                            action
                        ],
                        mouse,
                    ):
                        with self.lock:
                            self.policy.record_action(
                                x,
                                action,
                                p,
                            )

                    else:
                        with self.lock:
                            self.pause(
                                (
                                    "Wstrzymano akcję: "
                                    "brak fokusu UCN "
                                    "albo F12."
                                )
                            )

                thumb = (
                    frame.copy()
                )

                thumb.thumbnail(
                    (
                        768,
                        432,
                    )
                )

                out = io.BytesIO()

                thumb.save(
                    out,
                    format="JPEG",
                    quality=75,
                )

                with self.lock:
                    self.jpeg = (
                        out.getvalue()
                    )

                    self.ticks += 1

                    self.fps = (
                        1
                        / max(
                            (
                                time.monotonic()
                                - started
                            ),
                            0.001,
                        )
                    )

                if (
                    time.monotonic()
                    - self.last_save
                    > 30
                ):
                    with self.lock:
                        self.policy.save()

                    self.last_save = (
                        time.monotonic()
                    )

            except Exception:
                logging.exception(
                    "Experiment failed"
                )

                with self.lock:
                    self.pause(
                        (
                            "Błąd wykonania. "
                            "Zatrzymano sterowanie; "
                            "szczegóły w "
                            "logs/app.log."
                        )
                    )

            self.closed.wait(
                max(
                    0,
                    (
                        0.16
                        - (
                            time.monotonic()
                            - started
                        )
                    ),
                )
            )

    def state(self):
        with self.lock:
            counts = [
                len(q)
                for q
                in self.policy.samples
            ]

            return dict(
                application=(
                    "fly-ucn-local"
                ),
                mode=self.mode,
                note=self.note,
                action=self.action,
                actions=ACTIONS,
                probabilities=(
                    self.probabilities
                    .round(4)
                    .tolist()
                ),
                activity=(
                    self.brain.activity()
                ),
                groups=(
                    (
                        np.bincount(
                            self.brain.groups,
                            weights=abs(
                                self.brain.state
                            ),
                        )
                        / self.brain.group_sizes
                    )
                    .round(4)
                    .tolist()
                ),
                samples=(
                    self.policy.total_samples
                ),
                counts=counts,
                updates=(
                    self.policy.updates
                ),
                loss=round(
                    self.policy.loss,
                    4,
                ),
                ready=(
                    self.policy.ready
                ),
                reward=(
                    self.policy.reward_total
                ),
                history=list(
                    self.history
                ),
                fps=round(
                    min(
                        self.fps,
                        6.25,
                    ),
                    1,
                ),
                ticks=self.ticks,
                frame_time=(
                    self.frame_time
                ),
                focused=(
                    self.game.focused()
                    if self.game
                    else self.focused
                ),
                connected=bool(
                    self.game
                    and self.game.hwnd
                ),
                mouse=(
                    self.allow_mouse
                ),
                offline=(
                    self.offline
                ),
                episodes=(
                    self.episode_count
                ),
                wins=self.wins,
                templates=list(
                    self.templates
                ),
                elapsed=(
                    round(
                        (
                            time.monotonic()
                            - self.episode_start
                        ),
                        1,
                    )
                    if self.episode_start
                    else 0
                ),
                auto50=(
                    self.auto50_enabled
                ),
                auto50_status=(
                    self.auto50_status
                ),
                auto50_setup_difference=(
                    round(
                        self.auto50_setup_difference,
                        6,
                    )
                ),
                auto50_go_difference=(
                    round(
                        self.auto50_go_difference,
                        6,
                    )
                ),
            )

    def close(self):
        self.closed.set()

        if self.game:
            self.game.close()

        self.worker.join(
            timeout=5
        )

        with self.lock:
            self.policy.save()


def main():
    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8765,
    )

    parser.add_argument(
        "--no-browser",
        action="store_true",
    )

    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Explicit synthetic "
            "technical test, "
            "never game training"
        ),
    )

    parser.add_argument(
        "--auto50",
        action="store_true",
        help=(
            "Launch UCN and automatically "
            "start a verified 50/20 night"
        ),
    )

    args = parser.parse_args()

    url = (
        f"http://127.0.0.1:"
        f"{args.port}"
    )

    try:
        with urllib.request.urlopen(
            url + "/api/state",
            timeout=1,
        ) as response:
            existing = (
                json.load(
                    response
                )
            )

        if (
            existing.get(
                "application"
            )
            == "fly-ucn-local"
        ):
            print(
                "Program już działa:",
                url,
                flush=True,
            )

            if (
                not args.no_browser
                and not args.auto50
            ):
                webbrowser.open(
                    url
                )

            return

    except (
        OSError,
        ValueError,
    ):
        pass

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
            / "app.log"
        ),
        level=logging.INFO,
        encoding="utf-8",
        format=(
            "%(asctime)s %(message)s"
        ),
    )

    experiment = Experiment(
        offline=args.offline,
        auto50=args.auto50,
    )

    token = (
        secrets.token_urlsafe(
            32
        )
    )

    static = (
        ROOT
        / "ui"
    )

    class Handler(
        BaseHTTPRequestHandler
    ):
        def log_message(
            self,
            *args,
        ):
            pass

        def send(
            self,
            body,
            content="application/json",
            code=200,
        ):
            self.send_response(
                code
            )

            self.send_header(
                "Content-Type",
                content,
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
                "Cross-Origin-Resource-Policy",
                "same-origin",
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

        def valid_host(self):
            return (
                self.headers.get(
                    "Host"
                )
                in [
                    (
                        f"127.0.0.1:"
                        f"{args.port}"
                    ),
                    (
                        f"localhost:"
                        f"{args.port}"
                    ),
                ]
            )

        def do_GET(self):
            if not self.valid_host():
                return self.send(
                    b"{}",
                    code=403,
                )

            path = (
                self.path.split(
                    "?"
                )[0]
            )

            if (
                path
                == "/api/state"
            ):
                return self.send(
                    json.dumps(
                        experiment.state(),
                        ensure_ascii=False,
                    ).encode()
                )

            if (
                path
                == "/api/anatomy"
            ):
                return self.send(
                    json.dumps(
                        experiment.anatomy
                    ).encode()
                )

            if (
                path
                == "/api/frame"
            ):
                with experiment.lock:
                    jpeg = (
                        experiment.jpeg
                    )

                return self.send(
                    jpeg,
                    "image/jpeg",
                    (
                        200
                        if jpeg
                        else 204
                    ),
                )

            files = {
                "/": (
                    "index.html",
                    "text/html; charset=utf-8",
                ),
                "/app.js": (
                    "app.js",
                    "text/javascript; charset=utf-8",
                ),
                "/style.css": (
                    "style.css",
                    "text/css; charset=utf-8",
                ),
            }

            if path not in files:
                return self.send(
                    b"{}",
                    code=404,
                )

            name, mime = (
                files[path]
            )

            body = (
                (
                    static
                    / name
                )
                .read_text(
                    encoding="utf-8"
                )
                .replace(
                    "__TOKEN__",
                    token,
                )
            )

            self.send(
                body.encode(),
                mime,
            )

        def do_POST(self):
            origin = (
                self.headers.get(
                    "Origin"
                )
            )

            if (
                not self.valid_host()
                or self.path
                != "/api/command"
                or self.headers.get(
                    "X-Fly-Token"
                )
                != token
                or (
                    origin
                    and origin
                    not in [
                        (
                            "http://"
                            "127.0.0.1:"
                            f"{args.port}"
                        ),
                        (
                            "http://"
                            "localhost:"
                            f"{args.port}"
                        ),
                    ]
                )
            ):
                return self.send(
                    b"{}",
                    code=403,
                )

            try:
                size = int(
                    self.headers.get(
                        "Content-Length",
                        "0",
                    )
                )

                if not (
                    0
                    < size
                    < 2048
                ):
                    raise ValueError(
                        (
                            "Invalid "
                            "request size"
                        )
                    )

                data = json.loads(
                    self.rfile.read(
                        size
                    )
                )

                if (
                    not isinstance(
                        data,
                        dict,
                    )
                    or data.get(
                        "command"
                    )
                    not in [
                        "pause",
                        "stop",
                        "watch",
                        "teach",
                        "play",
                        "explore",
                        "positive",
                        "negative",
                        "win",
                        "loss",
                        "save",
                        "fit",
                        "mouse",
                        "stimulate",
                        "template",
                    ]
                ):
                    raise ValueError(
                        "Invalid command"
                    )

                if (
                    data[
                        "command"
                    ]
                    == "stimulate"
                    and data.get(
                        "group"
                    )
                    is not None
                    and not (
                        0
                        <= int(
                            data[
                                "group"
                            ]
                        )
                        < len(
                            experiment
                            .brain
                            .labels
                        )
                    )
                ):
                    raise ValueError(
                        "Invalid group"
                    )

                if (
                    data[
                        "command"
                    ]
                    == "stop"
                    and experiment.game
                ):
                    experiment.game.emergency.set()
                    experiment.game.release()

                experiment.commands.put(
                    data
                )

                self.send(
                    b'{"ok":true}'
                )

            except (
                ValueError,
                TypeError,
            ):
                self.send(
                    (
                        b'{"error":'
                        b'"Invalid command"}'
                    ),
                    code=400,
                )

    server = (
        ThreadingHTTPServer(
            (
                "127.0.0.1",
                args.port,
            ),
            Handler,
        )
    )

    experiment.worker.start()

    print(
        "Fly UCN:",
        url,
        flush=True,
    )

    # W AUTO50 nie otwieramy automatycznie
    # przeglądarki, ponieważ ukradłaby
    # fokus oknu UCN w trakcie konfiguracji.
    if (
        not args.no_browser
        and not args.auto50
    ):
        webbrowser.open(
            url
        )

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        pass

    finally:
        experiment.close()
        server.server_close()


if __name__ == "__main__":
    if '--auto50' in sys.argv:
        from autotrainer import main as auto_main
        sys.argv.remove('--auto50')
        auto_main()
    else:
        main()
