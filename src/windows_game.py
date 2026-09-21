"""Local UCN adapter: exact executable targeting, focus gate, F12 stop, no global recording."""

import ctypes as ct
from ctypes import wintypes as wt
from collections import deque
from pathlib import Path
import subprocess
import threading
import time

from PIL import ImageGrab


GAME_EXE = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Ultimate Custom Night\Ultimate Custom Night.exe"
)

u = ct.WinDLL(
    "user32",
    use_last_error=True,
)

k = ct.WinDLL(
    "kernel32",
    use_last_error=True,
)

u.GetForegroundWindow.restype = wt.HWND

u.WindowFromPoint.argtypes = [
    wt.POINT,
]
u.WindowFromPoint.restype = wt.HWND

u.GetAncestor.argtypes = [
    wt.HWND,
    wt.UINT,
]
u.GetAncestor.restype = wt.HWND

u.GetWindowThreadProcessId.argtypes = [
    wt.HWND,
    ct.POINTER(wt.DWORD),
]

u.IsWindowVisible.argtypes = [
    wt.HWND,
]

u.IsIconic.argtypes = [
    wt.HWND,
]

u.GetClientRect.argtypes = [
    wt.HWND,
    ct.POINTER(wt.RECT),
]

u.ClientToScreen.argtypes = [
    wt.HWND,
    ct.POINTER(wt.POINT),
]

u.GetAsyncKeyState.argtypes = [
    ct.c_int,
]
u.GetAsyncKeyState.restype = ct.c_short

u.SetForegroundWindow.argtypes = [
    wt.HWND,
]
u.SetForegroundWindow.restype = wt.BOOL

u.BringWindowToTop.argtypes = [
    wt.HWND,
]
u.BringWindowToTop.restype = wt.BOOL

u.ShowWindow.argtypes = [
    wt.HWND,
    ct.c_int,
]
u.ShowWindow.restype = wt.BOOL

u.SetCursorPos.argtypes = [
    ct.c_int,
    ct.c_int,
]
u.SetCursorPos.restype = wt.BOOL

k.OpenProcess.argtypes = [
    wt.DWORD,
    wt.BOOL,
    wt.DWORD,
]
k.OpenProcess.restype = wt.HANDLE

k.CloseHandle.argtypes = [
    wt.HANDLE,
]

k.QueryFullProcessImageNameW.argtypes = [
    wt.HANDLE,
    wt.DWORD,
    wt.LPWSTR,
    ct.POINTER(wt.DWORD),
]

try:
    u.SetProcessDpiAwarenessContext.argtypes = [
        ct.c_void_p
    ]

    u.SetProcessDpiAwarenessContext(
        ct.c_void_p(-4)
    )

except (
    AttributeError,
    OSError,
):
    pass


ULONG_PTR = wt.WPARAM


class KEYBDINPUT(ct.Structure):
    _fields_ = [
        (
            "wVk",
            wt.WORD,
        ),
        (
            "wScan",
            wt.WORD,
        ),
        (
            "dwFlags",
            wt.DWORD,
        ),
        (
            "time",
            wt.DWORD,
        ),
        (
            "dwExtraInfo",
            ULONG_PTR,
        ),
    ]


class MOUSEINPUT(ct.Structure):
    _fields_ = [
        (
            "dx",
            wt.LONG,
        ),
        (
            "dy",
            wt.LONG,
        ),
        (
            "mouseData",
            wt.DWORD,
        ),
        (
            "dwFlags",
            wt.DWORD,
        ),
        (
            "time",
            wt.DWORD,
        ),
        (
            "dwExtraInfo",
            ULONG_PTR,
        ),
    ]


class HARDWAREINPUT(ct.Structure):
    _fields_ = [
        (
            "uMsg",
            wt.DWORD,
        ),
        (
            "wParamL",
            wt.WORD,
        ),
        (
            "wParamH",
            wt.WORD,
        ),
    ]


class UNION(ct.Union):
    _fields_ = [
        (
            "ki",
            KEYBDINPUT,
        ),
        (
            "mi",
            MOUSEINPUT,
        ),
        (
            "hi",
            HARDWAREINPUT,
        ),
    ]


class INPUT(ct.Structure):
    _anonymous_ = (
        "data",
    )

    _fields_ = [
        (
            "type",
            wt.DWORD,
        ),
        (
            "data",
            UNION,
        ),
    ]


u.SendInput.argtypes = [
    wt.UINT,
    ct.POINTER(INPUT),
    ct.c_int,
]
u.SendInput.restype = wt.UINT

u.MapVirtualKeyW.argtypes = [
    wt.UINT,
    wt.UINT,
]
u.MapVirtualKeyW.restype = wt.UINT


KEYS = {
    **{
        x: ord(x)
        for x in "ADWFSZXC123456"
    },
    "SPACE": 0x20,
    "ENTER": 0x0D,
    "ESC": 0x1B,
}


HOTKEYS = {
    0x75: "teach",
    0x76: "play",
    0x77: "pause",
    0x78: "positive",
    0x79: "negative",
    0x7A: "win",
    0x7B: "stop",
}


def exe_for_window(hwnd):
    pid = wt.DWORD()

    u.GetWindowThreadProcessId(
        hwnd,
        ct.byref(pid),
    )

    handle = k.OpenProcess(
        0x1000,
        False,
        pid.value,
    )

    if not handle:
        return ""

    try:
        buf = ct.create_unicode_buffer(
            32768
        )

        n = wt.DWORD(
            len(buf)
        )

        return (
            buf.value
            if k.QueryFullProcessImageNameW(
                handle,
                0,
                buf,
                ct.byref(n),
            )
            else ""
        )

    finally:
        k.CloseHandle(
            handle
        )


class Game:
    def __init__(
        self,
        command,
    ):
        self.hwnd = None
        self.last_find = 0.0

        self.events = deque(
            maxlen=100
        )

        self.lock = threading.Lock()

        self.command = command

        self.emergency = (
            threading.Event()
        )

        self.closed = (
            threading.Event()
        )

        self.injected = set()

        self.input_lock = (
            threading.Lock()
        )

        self.observe_inputs = False

        self.thread = threading.Thread(
            target=self._sample,
            name="game-input",
            daemon=True,
        )

        self.thread.start()

    def process_id(self):
        hwnd=self.find()
        if not hwnd:return None
        process=wt.DWORD()
        u.GetWindowThreadProcessId(hwnd,ct.byref(process))
        return process.value or None

    def find(
        self,
        force=False,
    ):
        if (
            not force
            and time.monotonic()
            - self.last_find
            < 2
        ):
            return self.hwnd

        self.last_find = (
            time.monotonic()
        )

        found = []

        callback = ct.WINFUNCTYPE(
            wt.BOOL,
            wt.HWND,
            wt.LPARAM,
        )

        @callback
        def visit(
            hwnd,
            _,
        ):
            if (
                u.IsWindowVisible(hwnd)
                and exe_for_window(
                    hwnd
                ).casefold()
                == str(
                    GAME_EXE
                ).casefold()
            ):
                found.append(
                    hwnd
                )

            return True

        u.EnumWindows(
            visit,
            0,
        )

        self.hwnd = (
            found[0]
            if len(found) == 1
            else None
        )

        return self.hwnd

    def launch(self):
        """
        Launch UCN if it is not already running.

        Returns True if a new process was started.
        """

        if self.find(
            force=True
        ):
            return False

        if not GAME_EXE.exists():
            raise FileNotFoundError(
                (
                    "Nie znaleziono pliku gry: "
                    f"{GAME_EXE}"
                )
            )

        subprocess.Popen(
            [
                str(
                    GAME_EXE
                )
            ],
            cwd=str(
                GAME_EXE.parent
            ),
        )

        self.hwnd = None
        self.last_find = 0.0

        return True

    def wait_for_window(
        self,
        timeout=45.0,
    ):
        deadline = (
            time.monotonic()
            + max(
                0.0,
                float(timeout),
            )
        )

        while (
            time.monotonic()
            < deadline
        ):
            if (
                self.closed.is_set()
                or self.emergency.is_set()
            ):
                return False

            if self.find(
                force=True
            ):
                return True

            self.closed.wait(
                0.20
            )

        return False

    def activate(
        self,
        timeout=5.0,
    ):
        """
        Bring the UCN window to the foreground
        and confirm that it has focus.
        """

        hwnd = self.find(
            force=True
        )

        if not hwnd:
            return False

        deadline = (
            time.monotonic()
            + max(
                0.0,
                float(timeout),
            )
        )

        while (
            time.monotonic()
            < deadline
        ):
            if (
                self.closed.is_set()
                or self.emergency.is_set()
            ):
                return False

            if u.IsIconic(
                hwnd
            ):
                # SW_RESTORE
                u.ShowWindow(
                    hwnd,
                    9,
                )

            u.BringWindowToTop(
                hwnd
            )

            u.SetForegroundWindow(
                hwnd
            )

            if self.focused():
                return True

            time.sleep(
                0.10
            )

        return self.focused()

    def focused(self):
        return bool(
            self.hwnd
            and not u.IsIconic(
                self.hwnd
            )
            and u.GetForegroundWindow()
            == self.hwnd
        )

    def rect(self):
        if not self.hwnd:
            return None

        rect = wt.RECT()
        pt = wt.POINT(
            0,
            0,
        )

        if not u.GetClientRect(
            self.hwnd,
            ct.byref(rect),
        ):
            return None

        if not u.ClientToScreen(
            self.hwnd,
            ct.byref(pt),
        ):
            return None

        if (
            rect.right < 100
            or rect.bottom < 100
        ):
            return None

        return (
            pt.x,
            pt.y,
            pt.x + rect.right,
            pt.y + rect.bottom,
        )

    def capture(self):
        self.find()

        if not self.focused():
            return None

        rect = self.rect()

        if not rect:
            return None

        frame = ImageGrab.grab(
            bbox=rect,
            all_screens=True,
        )

        return (
            frame
            if self.focused()
            else None
        )

    def cursor(self):
        pt = wt.POINT()

        u.GetCursorPos(
            ct.byref(pt)
        )

        rect = self.rect()

        if not rect:
            return (
                0.5,
                0.5,
            )

        return (
            min(
                1,
                max(
                    0,
                    (
                        pt.x
                        - rect[0]
                    )
                    / (
                        rect[2]
                        - rect[0]
                    ),
                ),
            ),
            min(
                1,
                max(
                    0,
                    (
                        pt.y
                        - rect[1]
                    )
                    / (
                        rect[3]
                        - rect[1]
                    ),
                ),
            ),
        )

    def click_normalized(
        self,
        x,
        y,
    ):
        """
        Click a normalized point inside
        the UCN client area.
        """

        x = float(x)
        y = float(y)

        if (
            not 0.0 <= x <= 1.0
            or not 0.0 <= y <= 1.0
        ):
            raise ValueError(
                (
                    "Normalized click "
                    "coordinates must be "
                    "within 0..1"
                )
            )

        return self.perform(
            "CLICK",
            (
                x,
                y,
            ),
        )

    def consume(self):
        with self.lock:
            result = list(
                self.events
            )

            self.events.clear()

        return result

    def _sample(self):
        previous = {}
        last_mouse = (
            0.5,
            0.5,
        )

        while not self.closed.wait(
            0.01
        ):
            self.find()

            focused = (
                self.focused()
            )

            for (
                vk,
                cmd,
            ) in HOTKEYS.items():

                raw = (
                    u.GetAsyncKeyState(
                        vk
                    )
                )

                down = bool(
                    raw
                    & 0x8000
                )

                if (
                    (
                        down
                        or raw & 1
                    )
                    and not previous.get(
                        vk,
                        False,
                    )
                    and (
                        focused
                        or cmd
                        == "stop"
                    )
                ):
                    if (
                        cmd
                        == "stop"
                    ):
                        self.emergency.set()
                        self.release()

                    self.command(
                        cmd
                    )

                previous[
                    vk
                ] = down

            if (
                not focused
                or not self.observe_inputs
            ):
                for vk in KEYS.values():
                    previous[
                        vk
                    ] = bool(
                        u.GetAsyncKeyState(
                            vk
                        )
                        & 0x8000
                    )

                previous[
                    1
                ] = bool(
                    u.GetAsyncKeyState(
                        1
                    )
                    & 0x8000
                )

                last_mouse = (
                    self.cursor()
                    if focused
                    else (
                        0.5,
                        0.5,
                    )
                )

                continue

            mouse = (
                self.cursor()
            )

            events = []

            for (
                name,
                vk,
            ) in {
                **KEYS,
                "CLICK": 1,
            }.items():

                raw = (
                    u.GetAsyncKeyState(
                        vk
                    )
                )

                down = bool(
                    raw
                    & 0x8000
                )

                if (
                    (
                        down
                        or raw & 1
                    )
                    and not previous.get(
                        vk,
                        False,
                    )
                ):
                    events.append(
                        (
                            name,
                            mouse,
                        )
                    )

                previous[
                    vk
                ] = down

            if (
                abs(
                    mouse[0]
                    - last_mouse[0]
                )
                + abs(
                    mouse[1]
                    - last_mouse[1]
                )
                > 0.025
            ):
                events.append(
                    (
                        "MOVE",
                        mouse,
                    )
                )

                last_mouse = (
                    mouse
                )

            if events:
                with self.lock:
                    self.events.extend(
                        events
                    )

    def _send(
        self,
        item,
    ):
        if (
            u.SendInput(
                1,
                ct.byref(item),
                ct.sizeof(INPUT),
            )
            != 1
        ):
            raise OSError(
                ct.get_last_error(),
                "SendInput failed",
            )

    def _key(
        self,
        vk,
        up=False,
    ):
        item = INPUT(
            type=1
        )

        item.ki = KEYBDINPUT(
            0,
            u.MapVirtualKeyW(
                vk,
                0,
            ),
            (
                0x0008
                | (
                    0x0002
                    if up
                    else 0
                )
            ),
            0,
            0,
        )

        self._send(
            item
        )

    def release(self):
        with self.input_lock:
            for vk in list(
                self.injected
            ):
                try:
                    self._key(
                        vk,
                        True,
                    )
                except OSError:
                    pass

            self.injected.clear()

    def perform(self, action, mouse=(0.5, 0.5)):
        try:
            return self._perform(action, mouse)
        except OSError:
            # UAC/secure desktop can reject input between the focus check and key-up.
            self.emergency.set()
            self.release()
            self.command('pause')
            return False

    def _perform(
        self,
        action,
        mouse=(
            0.5,
            0.5,
        ),
    ):
        if (
            self.emergency.is_set()
            or not self.focused()
        ):
            return False

        if action == "WAIT":
            return True

        if action in [
            "MOVE",
            "CLICK",
            "HOLD_CLICK",
        ]:
            rect = self.rect()

            if not rect:
                return False

            pt = wt.POINT(
                rect[0]
                + int(
                    float(
                        mouse[0]
                    )
                    * (
                        rect[2]
                        - rect[0]
                        - 1
                    )
                ),
                rect[1]
                + int(
                    float(
                        mouse[1]
                    )
                    * (
                        rect[3]
                        - rect[1]
                        - 1
                    )
                ),
            )

            # Never click through an overlay
            # or another application.
            if (
                u.GetAncestor(
                    u.WindowFromPoint(
                        pt
                    ),
                    2,
                )
                != self.hwnd
            ):
                return False

            if (
                not self.focused()
                or self.emergency.is_set()
            ):
                return False

            if not u.SetCursorPos(
                pt.x,
                pt.y,
            ):
                return False

            if action in ("CLICK", "HOLD_CLICK"):
                item = INPUT(
                    type=0
                )

                item.mi = MOUSEINPUT(
                    0,
                    0,
                    0,
                    2,
                    0,
                    0,
                )

                try:
                    self._send(
                        item
                    )

                    self.emergency.wait(
                        0.4 if action == "HOLD_CLICK" else 0.025
                    )

                finally:
                    item.mi.dwFlags = 4

                    self._send(
                        item
                    )

            return True

        vk = KEYS[
            action
        ]

        try:
            with self.input_lock:
                if (
                    self.emergency.is_set()
                    or not self.focused()
                ):
                    return False

                self._key(
                    vk
                )

                self.injected.add(
                    vk
                )

            self.emergency.wait(
                (
                    1.5 if action == "ESC" else 0.065
                    if action
                    != "Z"
                    else 0.14
                )
            )

        finally:
            with self.input_lock:
                if (
                    vk
                    in self.injected
                ):
                    self._key(
                        vk,
                        True,
                    )

                    self.injected.discard(
                        vk
                    )

        return True

    def close(self):
        self.emergency.set()
        self.closed.set()
        self.release()
