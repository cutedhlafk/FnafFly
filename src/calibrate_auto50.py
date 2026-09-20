"""One-time AUTO50 coordinate calibration for the local UCN window."""

import ctypes as ct
import json
import time
from pathlib import Path

from windows_game import Game


ROOT = Path(__file__).resolve().parents[1]

CONFIG_PATH = (
    ROOT
    / "data"
    / "cache"
    / "auto50.json"
)

CONFIG_VERSION = 3

VK_F2 = 0x71
VK_F3 = 0x72
VK_F4 = 0x73
VK_F12 = 0x7B

user32 = ct.WinDLL(
    "user32",
    use_last_error=True,
)

user32.GetAsyncKeyState.argtypes = [
    ct.c_int,
]

user32.GetAsyncKeyState.restype = (
    ct.c_short
)


def key_down(vk):
    return bool(
        user32.GetAsyncKeyState(vk)
        & 0x8000
    )


def wait_until_released(vk):
    while key_down(vk):
        time.sleep(0.02)


def wait_for_key(game, vk, label):
    """
    Wait until the requested function key is pressed
    while UCN has focus.
    """

    print()
    print(label)
    print(
        "Najedz myszka na SRODEK przycisku "
        "i nacisnij odpowiedni klawisz."
    )

    wait_until_released(vk)

    previous = False

    while True:
        if (
            game.emergency.is_set()
            or key_down(VK_F12)
        ):
            raise KeyboardInterrupt

        current = key_down(vk)

        if current and not previous:
            if not game.focused():
                print(
                    "UCN nie ma fokusu. "
                    "Kliknij okno gry i sprobuj ponownie."
                )

                wait_until_released(vk)
                previous = False
                continue

            point = game.cursor()

            print(
                "Zapisano:",
                f"x={point[0]:.6f}",
                f"y={point[1]:.6f}",
            )

            wait_until_released(vk)

            return [
                round(
                    float(point[0]),
                    6,
                ),
                round(
                    float(point[1]),
                    6,
                ),
            ]

        previous = current

        time.sleep(0.02)


def validate_points(
    set_zero,
    set_twenty,
    go,
):
    points = {
        "set_all_0": set_zero,
        "set_all_20": set_twenty,
        "go": go,
    }

    for name, point in points.items():
        if len(point) != 2:
            raise ValueError(
                f"Niepoprawny punkt: {name}"
            )

        x = float(point[0])
        y = float(point[1])

        if not (
            0.0 <= x <= 1.0
            and 0.0 <= y <= 1.0
        ):
            raise ValueError(
                f"Punkt poza oknem: {name}"
            )

    def distance(a, b):
        return (
            (
                a[0] - b[0]
            )
            ** 2
            + (
                a[1] - b[1]
            )
            ** 2
        ) ** 0.5

    if (
        distance(
            set_zero,
            set_twenty,
        )
        < 0.01
    ):
        raise ValueError(
            "SET ALL 0 i SET ALL 20 "
            "sa praktycznie tym samym punktem."
        )

    if (
        distance(
            set_twenty,
            go,
        )
        < 0.01
    ):
        raise ValueError(
            "SET ALL 20 i GO "
            "sa praktycznie tym samym punktem."
        )


def main():
    print()
    print(
        "======================================="
    )
    print(
        "        AUTO50 - KALIBRACJA"
    )
    print(
        "======================================="
    )
    print()
    print(
        "Program uruchomi lub znajdzie UCN."
    )
    print()
    print(
        "Potem wykonasz tylko trzy czynnosci:"
    )
    print()
    print(
        "F2 = wskaz SET ALL 0"
    )
    print(
        "F3 = wskaz SET ALL 20"
    )
    print(
        "F4 = wskaz GO!"
    )
    print()
    print(
        "F12 = anuluj"
    )
    print()

    game = Game(
        lambda command: None
    )

    try:
        launched = game.launch()

        print(
            "Czekam na okno UCN..."
        )

        if not game.wait_for_window(
            timeout=60.0
        ):
            raise RuntimeError(
                "Nie znaleziono okna UCN."
            )

        if launched:
            print(
                "UCN zostalo uruchomione."
            )

            time.sleep(4.0)

        if not game.activate(
            timeout=10.0
        ):
            raise RuntimeError(
                "Nie udalo sie aktywowac UCN."
            )

        print()
        print(
            "UCN znalezione."
        )
        print(
            "Nie klikaj przyciskow mysza."
        )
        print(
            "Tylko NAJEDZ na ich srodek."
        )

        set_zero = wait_for_key(
            game,
            VK_F2,
            (
                "KROK 1/3: "
                "najedz na SET ALL 0 "
                "i nacisnij F2."
            ),
        )

        set_twenty = wait_for_key(
            game,
            VK_F3,
            (
                "KROK 2/3: "
                "najedz na SET ALL 20 "
                "i nacisnij F3."
            ),
        )

        go = wait_for_key(
            game,
            VK_F4,
            (
                "KROK 3/3: "
                "najedz na GO! "
                "i nacisnij F4."
            ),
        )

        validate_points(
            set_zero,
            set_twenty,
            go,
        )

        config = {
            "config_version": (
                CONFIG_VERSION
            ),
            "calibrated": True,
            "set_all_0": (
                set_zero
            ),
            "set_all_20": (
                set_twenty
            ),
            "go": go,
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

        CONFIG_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        CONFIG_PATH.write_text(
            json.dumps(
                config,
                indent=2,
            ),
            encoding="utf-8",
        )

        print()
        print(
            "======================================="
        )
        print(
            "KALIBRACJA ZAKONCZONA"
        )
        print(
            "======================================="
        )
        print()
        print(
            "SET ALL 0 :",
            set_zero,
        )
        print(
            "SET ALL 20:",
            set_twenty,
        )
        print(
            "GO!        :",
            go,
        )
        print()
        print(
            "Zapisano:"
        )
        print(
            CONFIG_PATH
        )
        print()
        print(
            "Teraz zamknij ten skrypt "
            "i uruchom START_FLY.bat."
        )

    except KeyboardInterrupt:
        print()
        print(
            "Kalibracja anulowana."
        )

    except Exception as exc:
        print()
        print(
            "BLAD KALIBRACJI:"
        )
        print(
            str(exc)
        )

    finally:
        game.close()

    print()
    input(
        "Nacisnij ENTER, aby zamknac..."
    )


if __name__ == "__main__":
    main()