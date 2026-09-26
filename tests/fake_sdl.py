"""Подделка модуля sdl2 (PySDL2): ровно то, что зовут sdlinput, service и rumble.

Поведение списано с настоящей SDL 2.28 там, где от него зависит WheelScript:

- при SDL_Init в очередь встают JOYDEVICEADDED для всех уже подключённых устройств
  (из-за этого сервис при старте перестраивает список дважды);
- SDL_JoystickOpen того же устройства возвращает тот же указатель и считает ссылки,
  SDL_JoystickClose закрывает только на последней;
- у отключённого устройства указатель живёт, пока его не закроют;
- haptic, закрытый у всё ещё открытого джойстика, заново не открывается
  (DirectInput у PXN V9, см. test_rumble.QuirkySDL);
- haptic, переживший свой джойстик, - обращение к освобождённой памяти: подделка
  записывает это в violations.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

SDL_INIT_JOYSTICK = 0x00000200
SDL_INIT_HAPTIC = 0x00001000
SDL_JOYAXISMOTION = 0x600
SDL_JOYBUTTONDOWN = 0x603
SDL_JOYDEVICEADDED = 0x605
SDL_JOYDEVICEREMOVED = 0x606
SDL_HAT_CENTERED = 0x00
SDL_HAT_UP = 0x01
SDL_HAT_RIGHT = 0x02
SDL_HAT_DOWN = 0x04
SDL_HAT_LEFT = 0x08


@dataclass
class Device:
    name: str = "V9GEN2"
    guid: str = "03000000ab1200000000000000000000"
    axes: list = field(default_factory=lambda: [0, 0, -32768])
    buttons: list = field(default_factory=lambda: [0] * 8)
    hats: list = field(default_factory=lambda: [SDL_HAT_CENTERED])
    player: int = -1
    haptic: bool = True
    fail_open: bool = False
    iid: int = -1              # instance id выдаёт FakeSDL.plug


class Handle:
    """То, что SDL_JoystickOpen возвращает вместо SDL_Joystick*."""

    def __init__(self, dev: Device):
        self.dev = dev
        self.refs = 0

    def __bool__(self):
        return True


class _JAxis:
    which = 0
    axis = 0
    value = 0


class _JDevice:
    which = 0


class Event:
    def __init__(self):
        self.type = 0
        self.jaxis = _JAxis()
        self.jdevice = _JDevice()


class Guid:
    def __init__(self, text):
        self.text = text


class FakeSDL:
    SDL_INIT_JOYSTICK = SDL_INIT_JOYSTICK
    SDL_INIT_HAPTIC = SDL_INIT_HAPTIC
    SDL_JOYAXISMOTION = SDL_JOYAXISMOTION
    SDL_JOYBUTTONDOWN = SDL_JOYBUTTONDOWN
    SDL_JOYDEVICEADDED = SDL_JOYDEVICEADDED
    SDL_JOYDEVICEREMOVED = SDL_JOYDEVICEREMOVED
    SDL_HAT_UP, SDL_HAT_RIGHT, SDL_HAT_DOWN, SDL_HAT_LEFT = SDL_HAT_UP, SDL_HAT_RIGHT, SDL_HAT_DOWN, SDL_HAT_LEFT
    SDL_Event = Event

    def __init__(self, *devices: Device, init_error: str = ""):
        self.lock = threading.RLock()
        self.devices: list[Device] = []     # подключены сейчас, по индексу устройства
        self.handles: dict[int, Handle] = {}  # instance id -> открытый указатель
        self.queue: list[tuple] = []
        self.next_iid = 0
        self.init_error = init_error
        self.inited = 0
        self.quit_called = False
        self.opens: list[str] = []           # имена при каждом настоящем открытии
        self.haptics: dict[int, Handle] = {}  # открытый haptic -> джойстик
        self.haptic_closed: set[int] = set()  # iid, у которых haptic закрыли при открытом джойстике
        self.haptic_opens: list[int] = []
        self.rumble: list[tuple] = []
        self.violations: list[str] = []
        self.error = b""
        for d in devices:
            self.plug(d, queue_event=False)

    # --- управление подделкой из теста ---

    def plug(self, dev: Device, queue_event: bool = True) -> Device:
        with self.lock:
            dev.iid = self.next_iid
            self.next_iid += 1
            self.devices.append(dev)
            if queue_event:
                self.queue.append((SDL_JOYDEVICEADDED, len(self.devices) - 1))
        return dev

    def unplug(self, dev: Device) -> None:
        with self.lock:
            self.devices.remove(dev)
            self.queue.append((SDL_JOYDEVICEREMOVED, dev.iid))

    def move(self, dev: Device, axis: int, value: int) -> None:
        with self.lock:
            dev.axes[axis] = value
            self.queue.append((SDL_JOYAXISMOTION, dev.iid, axis, value))

    def live(self) -> list[str]:
        with self.lock:
            return [h.dev.name for h in self.handles.values()]

    # --- SDL ---

    def SDL_Init(self, flags):  # noqa: N802
        if self.init_error:
            self.error = self.init_error.encode()
            return -1
        with self.lock:
            self.inited |= flags
            self.queue.extend((SDL_JOYDEVICEADDED, i) for i in range(len(self.devices)))
        return 0

    def SDL_WasInit(self, flags):  # noqa: N802
        return self.inited & flags

    def SDL_InitSubSystem(self, flags):  # noqa: N802
        self.inited |= flags
        return 0

    def SDL_Quit(self):  # noqa: N802
        self.quit_called = True
        if self.haptics:
            self.violations.append("SDL_Quit при открытом haptic")

    def SDL_GetError(self):  # noqa: N802
        return self.error

    def SDL_PollEvent(self, ev):  # noqa: N802
        with self.lock:
            if not self.queue:
                return 0
            item = self.queue.pop(0)
        ev.type = item[0]
        if item[0] == SDL_JOYAXISMOTION:
            ev.jaxis.which, ev.jaxis.axis, ev.jaxis.value = item[1], item[2], item[3]
        else:
            ev.jdevice.which = item[1]
        return 1

    def SDL_NumJoysticks(self):  # noqa: N802
        with self.lock:
            return len(self.devices)

    def SDL_JoystickGetDeviceInstanceID(self, index):  # noqa: N802
        with self.lock:
            return self.devices[index].iid if 0 <= index < len(self.devices) else -1

    def SDL_JoystickOpen(self, index):  # noqa: N802
        with self.lock:
            if not 0 <= index < len(self.devices):
                self.error = b"There are 0 joysticks available"
                return None
            dev = self.devices[index]
            if dev.fail_open:
                self.error = b"Couldn't open joystick"
                return None
            h = self.handles.get(dev.iid)
            if h is None:
                h = self.handles[dev.iid] = Handle(dev)
                self.opens.append(dev.name)
            h.refs += 1
            return h

    def SDL_JoystickClose(self, h):  # noqa: N802
        with self.lock:
            if h.refs <= 0:
                self.violations.append(f"лишний SDL_JoystickClose {h.dev.name}")
                return
            h.refs -= 1
            if h.refs == 0:
                del self.handles[h.dev.iid]
                self.haptic_closed.discard(h.dev.iid)
                if any(j is h for j in self.haptics.values()):
                    self.violations.append(f"haptic пережил свой джойстик {h.dev.name}")

    def SDL_JoystickInstanceID(self, h):  # noqa: N802
        return h.dev.iid

    def SDL_JoystickFromInstanceID(self, iid):  # noqa: N802
        with self.lock:
            return self.handles.get(iid)

    def SDL_JoystickName(self, h):  # noqa: N802
        return h.dev.name.encode("utf-8")

    def SDL_JoystickGetGUID(self, h):  # noqa: N802
        return Guid(h.dev.guid)

    def SDL_JoystickGetGUIDString(self, guid, buf, size):  # noqa: N802
        buf.value = guid.text.encode("ascii")[: size - 1]

    def SDL_JoystickNumAxes(self, h):  # noqa: N802
        return len(h.dev.axes)

    def SDL_JoystickNumButtons(self, h):  # noqa: N802
        return len(h.dev.buttons)

    def SDL_JoystickNumHats(self, h):  # noqa: N802
        return len(h.dev.hats)

    def SDL_JoystickGetAxis(self, h, a):  # noqa: N802
        return h.dev.axes[a]

    def SDL_JoystickGetButton(self, h, b):  # noqa: N802
        return h.dev.buttons[b]

    def SDL_JoystickGetHat(self, h, i):  # noqa: N802
        return h.dev.hats[i]

    def SDL_JoystickGetPlayerIndex(self, h):  # noqa: N802
        return h.dev.player

    # --- haptic ---

    def SDL_JoystickIsHaptic(self, h):  # noqa: N802
        return 1 if h.dev.haptic else 0

    def SDL_HapticOpenFromJoystick(self, h):  # noqa: N802
        with self.lock:
            if h.dev.iid in self.haptic_closed:
                self.error = b"Haptic: SDL_SYS_HapticOpenFromJoystick failed"
                return None
            hid = 1000 + h.dev.iid
            self.haptics[hid] = h
            self.haptic_opens.append(h.dev.iid)
            return hid

    def SDL_HapticRumbleSupported(self, hid):  # noqa: N802
        return 1

    def SDL_HapticRumbleInit(self, hid):  # noqa: N802
        return 0

    def SDL_HapticRumblePlay(self, hid, level, ms):  # noqa: N802
        self.rumble.append(("play", hid, level, ms))
        return 0

    def SDL_HapticRumbleStop(self, hid):  # noqa: N802
        self.rumble.append(("stop", hid))
        return 0

    def SDL_HapticClose(self, hid):  # noqa: N802
        with self.lock:
            j = self.haptics.pop(hid, None)
            if j is None:
                self.violations.append(f"SDL_HapticClose закрытого {hid}")
                return
            if j.dev.iid not in self.handles:
                self.violations.append(f"SDL_HapticClose после закрытия джойстика {j.dev.name}")
            else:
                self.haptic_closed.add(j.dev.iid)
