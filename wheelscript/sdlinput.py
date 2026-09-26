"""
Слой ввода на SDL2 без pygame: PySDL2 (обёртка ctypes) и SDL2.dll из пакета pysdl2-dll.

Версия SDL закреплена на 2.28.4 - той же, что привозил pygame 2.6.1. От неё зависят
GUID устройств (ими подписаны привязки в config.json), нормализация осей, порядок
устройств и причуды haptic у DirectInput. Та же библиотека - то же поведение руля.

Joystick повторяет то, как pygame переводил значения SDL в Python, поэтому сервис и
вибрация работают с ним так же, как раньше с pygame.joystick.Joystick:
ось = SDL_JoystickGetAxis / 32768.0, хатка = (x, y) с «вверх» = +1 по y.

Подсистема видео (pygame.display.init) не нужна: джойстикам SDL на Windows хватает
своего скрытого окна, а события включает сама SDL_INIT_JOYSTICK.
"""

from __future__ import annotations

import ctypes
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

PINNED = (2, 28, 4)

# До SDL_Init: без этого SDL перестаёт присылать события руля, когда в фокусе игра.
ENV = {"SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS": "1"}


class SdlError(Exception):
    pass


def load():
    """Модуль sdl2 с SDL2.dll из pysdl2-dll (в сборке она лежит в _internal/sdl2dll/dll).

    Путь задаём сами: иначе PySDL2 без pysdl2-dll взял бы любую SDL2.dll из PATH, а с ним
    ещё и печатал бы предупреждение «Using SDL2 binaries from pysdl2-dll» при каждом запуске.
    """
    for k, v in ENV.items():
        os.environ.setdefault(k, v)
    import sdl2dll
    os.environ["PYSDL2_DLL_PATH"] = sdl2dll.get_dllpath()
    import sdl2
    return sdl2


def version(sdl) -> tuple[int, int, int]:
    v = sdl.SDL_version()
    sdl.SDL_GetVersion(ctypes.byref(v))
    return (v.major, v.minor, v.patch)


def library_path(sdl) -> str:
    import sys
    return sys.modules[sdl.__name__ + ".dll"].get_dll_file()


def _error(sdl) -> str:
    try:
        e = sdl.SDL_GetError()
    except Exception:  # noqa: BLE001
        return "?"
    return (e.decode("utf-8", "replace") if isinstance(e, bytes) else str(e or "")) or "?"


class Joystick:
    """Открытое устройство SDL. Методы и значения - как у pygame.joystick.Joystick."""

    def __init__(self, sdl, ptr):
        self._sdl = sdl
        self.ptr = ptr
        self._iid = sdl.SDL_JoystickInstanceID(ptr)

    def get_instance_id(self) -> int:
        return self._iid

    def get_name(self) -> str:
        name = self._sdl.SDL_JoystickName(self.ptr)
        return name.decode("utf-8", "replace") if name else ""

    def get_guid(self) -> str:
        buf = ctypes.create_string_buffer(33)
        self._sdl.SDL_JoystickGetGUIDString(self._sdl.SDL_JoystickGetGUID(self.ptr), buf, 33)
        return buf.value.decode("ascii", "replace")

    def get_numaxes(self) -> int:
        return self._sdl.SDL_JoystickNumAxes(self.ptr)

    def get_numbuttons(self) -> int:
        return self._sdl.SDL_JoystickNumButtons(self.ptr)

    def get_numhats(self) -> int:
        return self._sdl.SDL_JoystickNumHats(self.ptr)

    def get_axis(self, i: int) -> float:
        v = self._sdl.SDL_JoystickGetAxis(self.ptr, i)
        return v / 32768.0 if v else 0.0

    def get_button(self, i: int) -> int:
        return 1 if self._sdl.SDL_JoystickGetButton(self.ptr, i) else 0

    def get_hat(self, i: int) -> tuple[int, int]:
        sdl, v = self._sdl, self._sdl.SDL_JoystickGetHat(self.ptr, i)
        x = 1 if v & sdl.SDL_HAT_RIGHT else -1 if v & sdl.SDL_HAT_LEFT else 0
        y = 1 if v & sdl.SDL_HAT_UP else -1 if v & sdl.SDL_HAT_DOWN else 0
        return (x, y)


class SdlInput:
    """Владелец SDL в потоке сервиса: инициализация, события, открытые устройства.

    Уже открытое устройство при новом scan() не переоткрывается: SDL (DirectInput) не
    может заново открыть haptic у джойстика, который всё ещё открыт, и руль терял бы
    вибрацию. Закрывает устройства только keep(): сервис зовёт его после того, как
    вибромотор отпустил отключённый руль, - haptic не должен пережить свой джойстик.
    """

    def __init__(self, sdl):
        self.sdl = sdl
        self._open: dict[int, Joystick] = {}
        self._event = sdl.SDL_Event()

    def init(self) -> None:
        if self.sdl.SDL_Init(self.sdl.SDL_INIT_JOYSTICK) != 0:
            raise SdlError(_error(self.sdl))

    def poll(self) -> tuple[bool, list[tuple[int, int]]]:
        """Разобрать очередь SDL: (устройства подключили или отключили, [(instance id, ось)] сдвинутых осей)."""
        sdl, ev = self.sdl, self._event
        changed, moved = False, []
        while sdl.SDL_PollEvent(ev) != 0:
            if ev.type in (sdl.SDL_JOYDEVICEADDED, sdl.SDL_JOYDEVICEREMOVED):
                changed = True
            elif ev.type == sdl.SDL_JOYAXISMOTION:
                moved.append((ev.jaxis.which, ev.jaxis.axis))
        return changed, moved

    def open(self, index: int) -> Joystick:
        j = self._open.get(self.sdl.SDL_JoystickGetDeviceInstanceID(index))
        if j is not None:
            return j
        ptr = self.sdl.SDL_JoystickOpen(index)
        if not ptr:
            raise SdlError(_error(self.sdl))
        j = Joystick(self.sdl, ptr)
        self._open[j.get_instance_id()] = j
        return j

    def scan(self) -> list[Joystick]:
        """Все подключённые сейчас устройства, по порядку SDL. Не открывшееся пропускается."""
        joys = []
        for i in range(self.sdl.SDL_NumJoysticks()):
            try:
                joys.append(self.open(i))
            except SdlError:
                log.exception("joystick %s open failed", i)
        return joys

    def keep(self, joys) -> None:
        """Закрыть все открытые устройства, кроме joys."""
        wanted = {id(j) for j in joys}
        for iid, j in list(self._open.items()):
            if id(j) not in wanted:
                del self._open[iid]
                self._close(j)

    def quit(self) -> None:
        self.keep([])
        try:
            self.sdl.SDL_Quit()
        except Exception:  # noqa: BLE001
            log.exception("SDL_Quit failed")

    def _close(self, j: Joystick) -> None:
        try:
            self.sdl.SDL_JoystickClose(j.ptr)
        except Exception:  # noqa: BLE001
            log.exception("joystick close failed")


def describe(sdl) -> str:
    """«2.28.4 <путь к SDL2.dll>» для самопроверки и лога; без исключений."""
    try:
        v: Optional[str] = ".".join(map(str, version(sdl)))
    except Exception:  # noqa: BLE001
        v = "?"
    try:
        path = library_path(sdl)
    except Exception:  # noqa: BLE001
        path = "?"
    return f"{v} {path}"
