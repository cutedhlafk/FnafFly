"""Local OCR of UCN states. Unknown images never count as survival or a win."""

from dataclasses import dataclass, field
import re

import numpy as np
from PIL import ImageOps
from mouse_controls import frame_mode


def clean(s):
    return re.sub(
        r"[^A-Z0-9]",
        "",
        s.upper(),
    )


@dataclass
class Observation:
    scene: str = "unknown"
    seconds: float | None = None
    buttons: dict = field(default_factory=dict)
    verified50: bool = False
    texts: list = field(default_factory=list)
    alerts: dict = field(default_factory=dict)
    temperature: float | None = None


def point_value_10000(normalized):
    """
    Verify 50/20 from Point Value = 10000.

    High Score must never count as verification.
    """

    if any(
        text == "POINTVALUE10000"
        for text, x, y, confidence in normalized
    ):
        return True

    for text, x, y, confidence in normalized:
        if text != "POINTVALUE":
            continue

        for value, vx, vy, value_confidence in normalized:
            if (
                value == "10000"
                and abs(vx - x) < 0.10
                and 0 < vy - y < 0.10
            ):
                return True

    return False


def classify(words):
    """
    Words:
    (text, normalized center x, center y, confidence).

    This function is intentionally independent from OCR
    so it can be covered by unit tests.
    """

    obs = Observation(
        texts=[
            word[0]
            for word in words
        ]
    )

    normalized = [
        (
            clean(text),
            x,
            y,
            confidence,
        )
        for (
            text,
            x,
            y,
            confidence,
        ) in words
        if confidence >= 0.55
    ]

    hud = any(
        re.fullmatch(
            r"(12|[1-5])AM",
            text,
        )
        and x > 0.8
        and y < 0.2
        for (
            text,
            x,
            y,
            confidence,
        ) in normalized
    )

    menu = [
        word
        for word in normalized
        if (
            "SETALL"
            in word[0]
            and word[1] > 0.75
        )
    ]

    #
    # SET ALL and 20 are often returned
    # by OCR as two separate lines.
    #
    for (
        text,
        x,
        y,
        confidence,
    ) in menu:
        if text != "SETALL":
            continue

        below = [
            word
            for word in normalized
            if (
                word[0] == "20"
                and abs(
                    word[1] - x
                ) < 0.07
                and 0
                < word[2] - y
                < 0.055
            )
        ]

        if below:
            obs.buttons[
                "twenty"
            ] = (
                x,
                (
                    y
                    + below[0][2]
                )
                / 2,
            )

    for (
        text,
        x,
        y,
        confidence,
    ) in normalized:
        if (
            text == "GO"
            and x > 0.7
            and y > 0.65
        ):
            obs.buttons[
                "go"
            ] = (
                x,
                y,
            )

        if (
            text == "SETALL20"
            and x > 0.75
        ):
            obs.buttons[
                "twenty"
            ] = (
                x,
                y,
            )

        if text in (
            "CLICKTOCONTINUE",
            "PRESSTOCONTINUE",
            "CONTINUE",
            "RETRY",
        ):
            obs.buttons[
                "continue"
            ] = (
                x,
                y,
            )

    joined = " ".join(
        word[0]
        for word in normalized
    )

    if len(menu) >= 2:
        obs.scene = "menu"

        levels = [
            text
            for (
                text,
                x,
                y,
                confidence,
            ) in normalized
            if (
                x < 0.86
                and y < 0.87
                and text == "20"
            )
        ]

        obs.verified50 = (
            len(levels) >= 50
            or point_value_10000(
                normalized
            )
        )

    elif (
        not hud
        and any(
            text
            in (
                "YOUDIDIT",
                "6AM",
            )
            and 0.2 < x < 0.8
            and 0.15 < y < 0.8
            for (
                text,
                x,
                y,
                confidence,
            ) in normalized
        )
    ):
        obs.scene = "win"

    elif (
        not hud
        and any(
            text == "GAMEOVER"
            and 0.2 < x < 0.8
            and 0.2 < y < 0.8
            for (
                text,
                x,
                y,
                confidence,
            ) in normalized
        )
    ):
        obs.scene = "loss"

    elif (
        "TAKETHISITEMFOR"
        in joined
        and "YOURTROUBLES"
        in joined
    ):
        obs.scene = "bonus"

    elif (
        sum(
            text
            in joined
            for text in (
                "POWERGENERATOR",
                "FLASHLIGHT",
                "CLOSELEFTDOOR",
                "CLOSERIGHTDOOR",
                "CLOSEFORWARDVENT",
            )
        )
        >= 3
    ):
        obs.scene = (
            "instructions"
        )

    else:
        for (
            text,
            x,
            y,
            confidence,
        ) in words:
            if (
                confidence < 0.55
                or x < 0.80
                or y > 0.20
            ):
                continue

            match = re.search(
                (
                    r"(?<!\d)"
                    r"(\d{1,2})"
                    r"\s*[:;]\s*"
                    r"(\d{2})"
                    r"(?:[.,](\d))?"
                ),
                text,
            )

            if (
                match
                and int(
                    match[2]
                ) < 60
            ):
                obs.seconds = (
                    int(
                        match[1]
                    )
                    * 60
                    + int(
                        match[2]
                    )
                    + int(
                        match[3]
                        or "0"
                    )
                    / 10
                )

        if (
            obs.seconds
            is not None
            or any(
                re.fullmatch(
                    r"(12|[1-5])AM",
                    text,
                )
                and x > 0.8
                and y < 0.2
                for (
                    text,
                    x,
                    y,
                    confidence,
                ) in normalized
            )
        ):
            obs.scene = (
                "playing"
            )

    #
    # Gameplay alerts.
    #
    if obs.scene in (
        "playing",
        "unknown",
    ):
        for (
            text,
            x,
            y,
            confidence,
        ) in normalized:
            if confidence < 0.85:
                continue

            if text == "MUTECALL":
                obs.alerts[
                    "mute_call"
                ] = (
                    x,
                    y,
                )

            if text == "SKIP":
                obs.alerts[
                    "skip_ad"
                ] = (
                    x,
                    y,
                )

            if (
                text
                == "RESETVENTILATION"
            ):
                obs.alerts[
                    "reset_vent"
                ] = (
                    x,
                    y,
                )

        for (
            text,
            x,
            y,
            confidence,
        ) in words:
            if (
                x > 0.85
                and y > 0.75
                and confidence >= 0.85
            ):
                match = re.fullmatch(
                    (
                        r"\s*"
                        r"(\d{2,3})"
                        r"\s*[°º]"
                        r"\s*[FC]?"
                        r"\s*"
                    ),
                    text,
                )

                if (
                    match
                    and 50
                    <= int(
                        match[1]
                    )
                    <= 130
                ):
                    obs.temperature = (
                        float(
                            match[1]
                        )
                    )

        if (
            obs.scene
            == "unknown"
            and obs.alerts
        ):
            obs.scene = (
                "interruption"
            )

    return obs


class ScreenReader:
    def __init__(self):
        import cv2
        # OCR shares the CPU with the full connectome simulation.
        cv2.setNumThreads(1)
        from rapidocr import (
            RapidOCR,
        )

        self.ocr = RapidOCR(
            params={
                (
                    "EngineConfig."
                    "onnxruntime."
                    "intra_op_num_threads"
                ): 2,
                (
                    "EngineConfig."
                    "onnxruntime."
                    "inter_op_num_threads"
                ): 1,
                "Global.use_cls":
                    False,
                # RapidOCR defaults to enlarging the SHORT side to 736px.
                # On HUD crops this expands a tiny image into a huge tensor.
                "Det.limit_type": "max",
                "Det.limit_side_len": 640,
                "Global.log_level":
                    "error",
            }
        )

        self.last_scene = (
            "unknown"
        )

        self.frame_index = 0

        #
        # Force ONNX lazy initialization here.
        #
        # This makes the first real game frame much
        # less likely to exceed the stale-frame limit.
        #
        self.ocr(
            np.zeros(
                (
                    96,
                    160,
                    3,
                ),
                dtype=np.uint8,
            )
        )

    def _remember(
        self,
        obs,
    ):
        self.last_scene = (
            obs.scene
        )

        return obs

    def _words(
        self,
        img,
        region=None,
    ):
        """
        OCR a selected normalized screen region.

        Coordinates from the crop are translated back
        to normalized coordinates of the full image.
        """

        if region is None:
            left = 0
            top = 0
            right = img.width
            bottom = img.height

        else:
            (
                x0,
                y0,
                x1,
                y1,
            ) = region

            left = max(
                0,
                min(
                    img.width - 1,
                    int(
                        img.width
                        * float(
                            x0
                        )
                    ),
                ),
            )

            top = max(
                0,
                min(
                    img.height - 1,
                    int(
                        img.height
                        * float(
                            y0
                        )
                    ),
                ),
            )

            right = max(
                left + 1,
                min(
                    img.width,
                    int(
                        img.width
                        * float(
                            x1
                        )
                    ),
                ),
            )

            bottom = max(
                top + 1,
                min(
                    img.height,
                    int(
                        img.height
                        * float(
                            y1
                        )
                    ),
                ),
            )

        crop = img.crop(
            (
                left,
                top,
                right,
                bottom,
            )
        )

        result = self.ocr(
            np.asarray(
                crop
            )[
                :,
                :,
                ::-1
            ].copy()
        )

        words = []

        if result.txts is None:
            return words

        for (
            text,
            box,
            score,
        ) in zip(
            result.txts,
            result.boxes,
            result.scores,
        ):
            center = (
                np.asarray(
                    box
                )
                .mean(
                    axis=0
                )
            )

            words.append(
                (
                    text,
                    float(
                        (
                            left
                            + center[0]
                        )
                        / img.width
                    ),
                    float(
                        (
                            top
                            + center[1]
                        )
                        / img.height
                    ),
                    float(
                        score
                    ),
                )
            )

        return words

    @staticmethod
    def _green_go(
        img,
    ):
        """
        Detect the large green GO button without OCR.
        """

        arr = np.asarray(
            img,
            dtype=np.float32,
        )

        green = (
            (
                arr[
                    :,
                    :,
                    1,
                ]
                > 65
            )
            & (
                arr[
                    :,
                    :,
                    1,
                ]
                > arr[
                    :,
                    :,
                    0,
                ]
                * 1.12
            )
            & (
                arr[
                    :,
                    :,
                    1,
                ]
                > arr[
                    :,
                    :,
                    2,
                ]
                * 1.30
            )
        )

        #
        # GO lives in the lower-right corner.
        #
        green[
            :int(
                img.height
                * 0.80
            ),
            :,
        ] = False

        green[
            :,
            :int(
                img.width
                * 0.85
            ),
        ] = False

        yy, xx = np.where(
            green
        )

        if (
            len(xx)
            > img.width
            * img.height
            * 0.004
        ):
            return (
                float(
                    np.median(
                        xx
                    )
                    / img.width
                ),
                float(
                    np.median(
                        yy
                    )
                    / img.height
                ),
            )

        return None

    def _menu(
        self,
        img,
    ):
        """
        Fast menu reader.

        Do NOT OCR character tiles or character
        descriptions. They were the reason a single
        menu read could take 9-17 seconds.
        """

        #
        # Only the vertical SET ALL button group.
        #
        controls = self._words(
            img,
            (
                0.80,
                0.01,
                0.995,
                0.42,
            ),
        )

        #
        # Point Value / High Score area.
        #
        score = self._words(
            img,
            (
                0.72,
                0.44,
                0.995,
                0.70,
            ),
        )

        words = (
            controls
            + score
        )

        normalized = [
            (
                clean(text),
                x,
                y,
                confidence,
            )
            for (
                text,
                x,
                y,
                confidence,
            ) in words
            if confidence >= 0.55
        ]

        set_all_count = sum(
            "SETALL"
            in text
            for (
                text,
                x,
                y,
                confidence,
            ) in normalized
        )

        menu_evidence = (
            set_all_count >= 1
            or any(
                "POINTVALUE"
                in text
                for (
                    text,
                    x,
                    y,
                    confidence,
                ) in normalized
            )
        )

        if not menu_evidence:
            return None

        obs = classify(
            words
        )

        #
        # Because this OCR was taken from known menu
        # regions, even one reliable SET ALL is enough
        # to identify the menu.
        #
        obs.scene = "menu"

        if point_value_10000(
            normalized
        ):
            obs.verified50 = (
                True
            )

        go = self._green_go(
            img
        )

        if go is not None:
            obs.buttons[
                "go"
            ] = go

        return obs

    def _gameplay(
        self,
        img,
    ):
        """
        Fast gameplay HUD reader.
        """

        hud_words = self._words(
            img,
            (
                0.79,
                0.0,
                1.0,
                0.20,
            ),
        )

        obs = classify(
            hud_words
        )

        if (
            obs.scene
            != "playing"
        ):
            return None

        #
        # Temperature is small and isolated,
        # so reading it separately is cheap.
        #
        temperature_words = (
            self._words(
                img,
                (
                    0.84,
                    0.74,
                    1.0,
                    1.0,
                ),
            )
        )

        words = (
            hud_words
            + temperature_words
        )

        # Keep camera labels at readable size instead of shrinking them with
        # the entire screen. Three labels confirm that the camera map is open.
        if self.frame_index % 2 == 0 and frame_mode(img) == 'monitor':
            words.extend(self._words(img, (.48, .40, .81, .88)))

        #
        # Every fourth gameplay read, use a heavily
        # reduced frame to search for large alerts.
        #
        # It preserves MUTE CALL / RESET VENTILATION
        # support without running expensive 1280x720
        # full-frame OCR every cycle.
        #
        if (
            self.frame_index
            % 4
            == 0
        ):
            # Only alert controls, not dozens of labels and animatronic art.
            regions=((.35,.68,.65,.90),(.0,.15,.35,.40),(.65,.65,1.,.90))
            words.extend(self._words(img, regions[(self.frame_index//4)%len(regions)]))

        return classify(
            words
        )

    def _dark_terminal(
        self,
        img,
    ):
        """
        Check dark result screens with a central crop.
        """

        gray = np.asarray(
            img.convert(
                "L"
            )
        )

        dark_enough = (
            float(
                np.mean(
                    gray > 28
                )
            )
            <= 0.20
        )

        if not dark_enough:
            return None

        crop = img.crop(
            (
                int(
                    img.width
                    * 0.25
                ),
                int(
                    img.height
                    * 0.25
                ),
                int(
                    img.width
                    * 0.75
                ),
                int(
                    img.height
                    * 0.80
                ),
            )
        )

        enhanced = (
            ImageOps
            .autocontrast(
                crop.convert(
                    "L"
                )
            )
            .convert(
                "RGB"
            )
        )

        result = self.ocr(
            np.asarray(
                enhanced
            )[
                :,
                :,
                ::-1
            ].copy()
        )

        if result.txts is None:
            return None

        texts = []

        for (
            text,
            score,
        ) in zip(
            result.txts,
            result.scores,
        ):
            texts.append(
                text
            )

            if (
                float(
                    score
                )
                < 0.70
            ):
                continue

            normalized = clean(
                text
            )

            if (
                "GAMEOVER"
                in normalized
            ):
                return Observation(
                    scene="loss",
                    texts=texts,
                )

            if (
                "YOUDIDIT"
                in normalized
            ):
                return Observation(
                    scene="win",
                    texts=texts,
                )

        return None

    def _fallback(
        self,
        img,
    ):
        """
        Reduced-resolution fallback for rare screens.

        Never send the 1280x720 text-heavy menu through
        full-frame OCR.
        """

        small = img.copy()

        small.thumbnail(
            (
                640,
                360,
            )
        )

        words = self._words(
            small
        )

        obs = classify(
            words
        )

        if (
            obs.scene
            == "loss"
        ):
            #
            # Toy Freddy can show GAME OVER on
            # his television while our night is alive.
            #
            gray = np.asarray(
                img.convert(
                    "L"
                )
            )

            dark_enough = (
                float(
                    np.mean(
                        gray > 28
                    )
                )
                <= 0.20
            )

            if not dark_enough:
                obs.scene = (
                    "unknown"
                )

        go = self._green_go(
            img
        )

        if (
            obs.scene
            in (
                "menu",
                "instructions",
            )
            and go
            is not None
        ):
            obs.buttons[
                "go"
            ] = go

        return obs

    def read(
        self,
        frame,
    ):
        """
        Read one UCN frame without blocking the
        training loop with full-HD OCR.
        """

        self.frame_index += 1

        img = frame.convert(
            "RGB"
        )

        #
        # 960x540 is enough for UCN labels but much
        # cheaper than the native 1920x1080 capture.
        #
        img.thumbnail(
            (
                960,
                540,
            )
        )

        # Result screens contain little text; avoid scanning every HUD region
        # before acknowledging a loss and returning to the menu.
        if self.last_scene in ('loss', 'win'):
            terminal = self._dark_terminal(img)
            if terminal is not None:
                return self._remember(terminal)

        #
        # Once a night has started, try the tiny HUD
        # first. Do not waste time checking the menu
        # before every gameplay OCR cycle.
        #
        if self.last_scene in (
            "playing",
            "interruption",
        ):
            gameplay = (
                self._gameplay(
                    img
                )
            )

            if gameplay is not None:
                return self._remember(
                    gameplay
                )

        #
        # Menu fast path.
        #
        menu = self._menu(
            img
        )

        if menu is not None:
            return self._remember(
                menu
            )

        #
        # If this was not a menu, try the gameplay HUD.
        #
        gameplay = self._gameplay(
            img
        )

        if gameplay is not None:
            return self._remember(
                gameplay
            )

        #
        # Instructions have a large green GO button.
        #
        # We only interpret it this way AFTER the
        # dedicated menu scan failed, preventing the
        # normal character menu from being mistaken
        # for instructions.
        #
        go = self._green_go(
            img
        )

        # Green pixels alone are not proof of an instruction screen. The
        # first two instruction rows prove the screen without OCR of the large
        # keyboard drawing (dozens of expensive single-character recognitions).
        if go is not None:
            instructions=classify(self._words(img,(.27,.08,.73,.20)))
            if instructions.scene=='instructions':
                instructions.buttons['go']=go
                return self._remember(instructions)

        terminal = (
            self._dark_terminal(
                img
            )
        )

        if terminal is not None:
            return self._remember(
                terminal
            )

        #
        # Rare screen fallback.
        #
        # This is only 640x360, never the text-heavy
        # native/full menu frame.
        #
        return self._remember(
            self._fallback(
                img
            )
        )
