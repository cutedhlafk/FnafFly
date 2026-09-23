"""Automatic startup of a calibrated UCN 50/20 night."""

from dataclasses import dataclass
from pathlib import Path
import json
import time

import numpy as np


ROOT = Path(__file__).resolve().parent

CONFIG_PATH = (
    ROOT
    / "data"
    / "cache"
    / "auto50.json"
)

CONFIG_VERSION = 3


@dataclass(frozen=True)
class Auto50Result:
    ok: bool
    message: str
    setup_difference: float = 0.0
    go_difference: float = 0.0


class Auto50Bootstrap:
    """
    Start Ultimate Custom Night and select 50/20
    using coordinates calibrated on this computer.
    """

    def __init__(
        self,
        game,
        reader=None,
    ):
        self.game = game
        self.reader = reader

        self.config = (
            self._load_config()
        )

    def _load_config(
        self,
    ):
        if not CONFIG_PATH.exists():
            return None

        try:
            config = json.loads(
                CONFIG_PATH.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            ValueError,
            TypeError,
        ):
            return None

        if not isinstance(
            config,
            dict,
        ):
            return None

        try:
            version = int(
                config.get(
                    "config_version",
                    0,
                )
            )

        except (
            ValueError,
            TypeError,
        ):
            return None

        if (
            version
            != CONFIG_VERSION
        ):
            return None

        if not bool(
            config.get(
                "calibrated",
                False,
            )
        ):
            return None

        required = [
            "set_all_0",
            "set_all_20",
            "go",
        ]

        for name in required:
            point = config.get(
                name
            )

            if (
                not isinstance(
                    point,
                    list,
                )
                or len(point) != 2
            ):
                return None

            try:
                x = float(
                    point[0]
                )

                y = float(
                    point[1]
                )

            except (
                ValueError,
                TypeError,
            ):
                return None

            if not (
                0.0 <= x <= 1.0
                and 0.0 <= y <= 1.0
            ):
                return None

        defaults = {
            "after_focus_seconds": 2.0,
            "after_click_seconds": 0.8,
            "after_go_seconds": 2.5,
            "minimum_setup_difference": (
                0.0025
            ),
            "minimum_go_difference": (
                0.025
            ),
        }

        for name, value in (
            defaults.items()
        ):
            if name not in config:
                config[name] = value
            try:
                config[name] = float(config[name])
            except (ValueError, TypeError):
                return None
            limit = 30. if name.endswith('_seconds') else 1.
            if not np.isfinite(config[name]) or not 0 < config[name] <= limit:
                return None

        return config

    @staticmethod
    def _gray(
        frame,
    ):
        return (
            np.asarray(
                frame.convert(
                    "L"
                ),
                dtype=np.float32,
            )
            / 255.0
        )

    @classmethod
    def _difference(
        cls,
        first,
        second,
        left_fraction=1.0,
    ):
        if (
            first is None
            or second is None
        ):
            return 0.0

        if (
            first.size
            != second.size
        ):
            return 0.0

        first_gray = cls._gray(
            first
        )

        second_gray = cls._gray(
            second
        )

        if (
            first_gray.shape
            != second_gray.shape
        ):
            return 0.0

        width = max(
            1,
            int(
                first_gray.shape[1]
                * float(
                    left_fraction
                )
            ),
        )

        return float(
            np.abs(
                first_gray[
                    :,
                    :width,
                ]
                - second_gray[
                    :,
                    :width,
                ]
            ).mean()
        )

    def _wait(
        self,
        seconds,
    ):
        deadline = (
            time.monotonic()
            + max(
                0.0,
                float(seconds),
            )
        )

        while (
            time.monotonic()
            < deadline
        ):
            if (
                self.game
                .emergency
                .is_set()
                or self.game
                .closed
                .is_set()
                or not self.game.focused()
            ):
                return False

            remaining = (
                deadline
                - time.monotonic()
            )

            time.sleep(
                min(
                    0.05,
                    max(
                        0.0,
                        remaining,
                    ),
                )
            )

        return True

    def _point(
        self,
        name,
    ):
        point = (
            self.config[
                name
            ]
        )

        return (
            float(
                point[0]
            ),
            float(
                point[1]
            ),
        )

    def run(
        self,
    ):
        if self.config is None:
            return Auto50Result(
                False,
                (
                    "AUTO50 nie jest "
                    "skalibrowane. Uruchom "
                    "najpierw "
                    "CALIBRATE_AUTO50.bat."
                ),
            )

        if (
            self.game
            .emergency
            .is_set()
        ):
            return Auto50Result(
                False,
                (
                    "AUTO50 przerwane "
                    "przez F12."
                ),
            )

        try:
            launched = (
                self.game.launch()
            )

        except (
            OSError,
            FileNotFoundError,
        ) as exc:
            return Auto50Result(
                False,
                (
                    "Nie udalo sie "
                    "uruchomic UCN: "
                    f"{exc}"
                ),
            )

        if not (
            self.game
            .wait_for_window(
                timeout=60.0
            )
        ):
            return Auto50Result(
                False,
                (
                    "Nie znaleziono "
                    "okna UCN."
                ),
            )

        if launched:
            if not self._wait(
                4.0
            ):
                return Auto50Result(
                    False,
                    (
                        "AUTO50 przerwane "
                        "przez F12."
                    ),
                )

        if not (
            self.game.activate(
                timeout=10.0
            )
        ):
            return Auto50Result(
                False,
                (
                    "Nie udalo sie "
                    "aktywować UCN."
                ),
            )

        if not self._wait(
            self.config[
                "after_focus_seconds"
            ]
        ):
            return Auto50Result(
                False,
                (
                    "AUTO50 przerwane "
                    "przez F12."
                ),
            )

        #
        # SET ALL 0
        #
        if self.reader is None:
            from screen_reader import ScreenReader
            self.reader = ScreenReader()
        menu_frame = self.game.capture()
        if menu_frame is None or self.reader.read(menu_frame).scene != 'menu':
            return Auto50Result(False, 'AUTO50: brak potwierdzonego menu; pomijam kliknięcia.')
        if not (
            self.game
            .click_normalized(
                *self._point(
                    "set_all_0"
                )
            )
        ):
            return Auto50Result(
                False,
                (
                    "Nie udalo sie "
                    "kliknac SET ALL 0."
                ),
            )

        if not self._wait(
            self.config[
                "after_click_seconds"
            ]
        ):
            return Auto50Result(
                False,
                (
                    "AUTO50 przerwane "
                    "przez F12."
                ),
            )

        zero_frame = (
            self.game.capture()
        )

        if zero_frame is None:
            return Auto50Result(
                False,
                (
                    "Brak obrazu po "
                    "SET ALL 0."
                ),
            )

        #
        # SET ALL 20
        #
        if not (
            self.game
            .click_normalized(
                *self._point(
                    "set_all_20"
                )
            )
        ):
            return Auto50Result(
                False,
                (
                    "Nie udalo sie "
                    "kliknac SET ALL 20."
                ),
            )

        if not self._wait(
            self.config[
                "after_click_seconds"
            ]
        ):
            return Auto50Result(
                False,
                (
                    "AUTO50 przerwane "
                    "przez F12."
                ),
            )

        twenty_frame = (
            self.game.capture()
        )

        if twenty_frame is None:
            return Auto50Result(
                False,
                (
                    "Brak obrazu po "
                    "SET ALL 20."
                ),
            )

        setup_difference = (
            self._difference(
                zero_frame,
                twenty_frame,
                left_fraction=0.78,
            )
        )

        minimum_setup = float(
            self.config[
                "minimum_setup_difference"
            ]
        )

        if (
            setup_difference
            < minimum_setup
        ):
            return Auto50Result(
                False,
                (
                    "Kliknieto zapisany "
                    "punkt SET ALL 20, "
                    "ale siatka postaci "
                    "nie zmienila sie "
                    "wystarczajaco. "
                    "Uruchom ponownie "
                    "CALIBRATE_AUTO50.bat "
                    "i wskaz dokladny "
                    "srodek przycisku."
                ),
                setup_difference=(
                    setup_difference
                ),
            )

        #
        # GO!
        #
        configured = self.reader.read(twenty_frame)
        if configured.scene != 'menu' or not configured.verified50:
            return Auto50Result(False, 'AUTO50: OCR nie potwierdził 50/20. Nie uruchamiam nocy.', setup_difference)
        before_go = (
            twenty_frame
        )

        if not (
            self.game
            .click_normalized(
                *self._point(
                    "go"
                )
            )
        ):
            return Auto50Result(
                False,
                (
                    "Nie udalo sie "
                    "kliknac GO."
                ),
                setup_difference=(
                    setup_difference
                ),
            )

        if not self._wait(
            self.config[
                "after_go_seconds"
            ]
        ):
            return Auto50Result(
                False,
                (
                    "AUTO50 przerwane "
                    "przez F12."
                ),
                setup_difference=(
                    setup_difference
                ),
            )

        after_go = (
            self.game.capture()
        )

        if after_go is None:
            return Auto50Result(
                False,
                (
                    "Brak obrazu po GO; start niepotwierdzony."
                ),
                setup_difference=(
                    setup_difference
                ),
                go_difference=0.0,
            )

        go_difference = (
            self._difference(
                before_go,
                after_go,
            )
        )

        minimum_go = float(
            self.config[
                "minimum_go_difference"
            ]
        )

        if (
            go_difference
            < minimum_go
        ):
            return Auto50Result(
                False,
                (
                    "SET ALL 20 zostalo "
                    "ustawione, ale "
                    "klikniecie GO "
                    "nie zmienilo ekranu. "
                    "Skalibruj punkt GO "
                    "ponownie."
                ),
                setup_difference=(
                    setup_difference
                ),
                go_difference=(
                    go_difference
                ),
            )

        return Auto50Result(
            True,
            (
                "50/20 ustawione "
                "i noc uruchomiona "
                "automatycznie."
            ),
            setup_difference=(
                setup_difference
            ),
            go_difference=(
                go_difference
            ),
        )
