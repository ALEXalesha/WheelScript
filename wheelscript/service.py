"""
Фоновый поток: единственный владелец SDL (sdlinput). Опрашивает все подключённые
джойстики/рули, отдаёт снимок состояния интерфейсу и гоняет движок.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional

from . import sdlinput, sendinput
from .engine import DeviceState, Engine
from .gamepad import VirtualPad
from .model import PAD_ACTIONS, Profile
from .rumble import RumbleRelay, WheelHaptic, player_index

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceInfo:
    key: str
    name: str
    axes: int
    buttons: int
    hats: int


class InputService:
    def __init__(self, tick_rate: int = 125):
        self._lock = threading.Lock()
        self._cmds: queue.SimpleQueue = queue.SimpleQueue()
        self.events: queue.SimpleQueue = queue.SimpleQueue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="wheel-input", daemon=True)
        self._engine = Engine(enabled=False)
        self._states: dict[str, DeviceState] = {}
        self._infos: list[DeviceInfo] = []
        self._joys: list = []
        self._input: Optional[sdlinput.SdlInput] = None
        self._known: dict[str, set[int]] = {}
        self._suspend = 0
        self._toggle_key = "f8"
        self._tick = 1.0 / tick_rate
        self._enabled = False
        self._has_pad = False
        self.pad_status = "не используется"
        self._relay = RumbleRelay()
        self._haptic = WheelHaptic()
        self._rumble = 1.0
        self.rumble_status = ""
        self._pad = VirtualPad(self._on_pad_status, self._relay.set_game)
        self._own_slot: Optional[int] = None  # XInput-слот нашего геймпада: его не читаем как ввод

    def _on_pad_status(self, text: str) -> None:
        self.pad_status = text
        self.events.put(("pad_status", text))

    # --- API для интерфейса (потокобезопасно) ---

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._thread.join(timeout)

    def snapshot(self) -> tuple[dict[str, DeviceState], list[DeviceInfo]]:
        with self._lock:
            return dict(self._states), list(self._infos)

    def device_names(self) -> dict[str, str]:
        with self._lock:
            return {d.key: d.name for d in self._infos}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_profile(self, profile: Profile) -> None:
        self._cmds.put(("profile", profile))

    def set_enabled(self, flag: bool) -> None:
        self._cmds.put(("enabled", flag))

    def toggle(self) -> None:
        self._cmds.put(("toggle", None))

    def suspend(self) -> None:
        self._cmds.put(("suspend", 1))

    def resume(self) -> None:
        self._cmds.put(("suspend", -1))

    def set_toggle_key(self, name: str) -> None:
        self._cmds.put(("toggle_key", name))

    def set_tick_rate(self, hz: int) -> None:
        self._cmds.put(("tick", hz))

    def set_rumble(self, strength: float) -> None:
        self._cmds.put(("rumble", strength))

    def rumble_test(self) -> None:
        self._cmds.put(("rumble_test", None))

    # --- поток ---

    def _run(self) -> None:
        try:
            self._input = sdlinput.SdlInput(sdlinput.load())
            self._input.init()
        except Exception as e:  # noqa: BLE001
            log.exception("SDL init failed")
            self.events.put(("error", f"Не удалось инициализировать SDL: {e}"))
            return
        log.info("SDL %s", sdlinput.describe(self._input.sdl))
        self._rebuild()
        last = time.perf_counter()
        toggle_prev = False
        try:
            while not self._stop.is_set():
                started = time.perf_counter()
                out: list = []
                try:
                    out += self._drain_commands()
                    rebuild = self._pump()
                    slot = self._pad.slot
                    if slot != self._own_slot:  # свой геймпад появился или исчез — пересобрать список
                        self._own_slot = slot
                        rebuild = True
                    if rebuild:
                        out += self._engine.release_all()
                        self._rebuild()
                    states = self._read()
                    with self._lock:
                        self._states = states
                    now = time.perf_counter()
                    dt, last = now - last, now
                    default = next(iter(states), None)
                    if self._suspend == 0:
                        down = bool(self._toggle_key) and sendinput.is_key_down(self._toggle_key)
                        if down and not toggle_prev:
                            out += self._engine.set_enabled(not self._engine.enabled)
                        toggle_prev = down
                        out += self._engine.step(states, dt, default)
                except Exception as e:  # noqa: BLE001
                    log.exception("input loop error")
                    out += self._engine.release_all()
                    self.events.put(("error", str(e)))
                self._apply(out)
                self._rumble_tick()
                spare = self._tick - (time.perf_counter() - started)
                if spare > 0:
                    time.sleep(spare)
        finally:
            self._apply(self._engine.release_all())
            self._haptic.close()
            self._pad.close()
            self._joys = []
            self._input.quit()

    def _drain_commands(self) -> list:
        out: list = []
        while True:
            try:
                cmd, arg = self._cmds.get_nowait()
            except queue.Empty:
                return out
            if cmd == "profile":
                with self._lock:
                    states = dict(self._states)
                out += self._engine.set_profile(arg, states, next(iter(states), None))
                self._has_pad = any(b.enabled and b.action.kind in PAD_ACTIONS for b in arg.bindings)
                if self._has_pad and self._engine.enabled:
                    self._pad.apply(self._engine.pad_state)
            elif cmd == "enabled":
                out += self._engine.set_enabled(bool(arg))
            elif cmd == "toggle":
                out += self._engine.set_enabled(not self._engine.enabled)
            elif cmd == "suspend":
                was = self._suspend
                self._suspend = max(0, self._suspend + arg)
                if was == 0 and self._suspend > 0:
                    out += self._engine.release_all()
                elif was > 0 and self._suspend == 0:
                    with self._lock:
                        states = dict(self._states)
                    self._engine.block_active(states, next(iter(states), None))
            elif cmd == "toggle_key":
                self._toggle_key = arg or ""
            elif cmd == "tick":
                self._tick = 1.0 / max(20, min(1000, int(arg)))
            elif cmd == "rumble":
                self._rumble = max(0.0, min(1.0, float(arg))) if arg == arg else 0.0
            elif cmd == "rumble_test":
                self._relay.test(time.monotonic(), self._rumble)

    def _rumble_tick(self) -> None:
        # Вибрация только пока маппинг работает: на паузе (открыт редактор) и после
        # выключения руль молчит, даже если игра всё ещё «вибрирует» геймпадом.
        try:
            cmd = self._relay.tick(time.monotonic(), self._engine.enabled and self._suspend == 0, self._rumble)
            if cmd is not None:
                self._haptic.apply(cmd)
        except Exception:  # noqa: BLE001
            log.exception("rumble tick failed")

    def _apply(self, events: list) -> None:
        for ev in events:
            if ev[0] == "enabled":
                self._enabled = ev[1]
                self.events.put(ev)
                if not ev[1]:
                    self._relay.reset()
                # Геймпад «вставляем» сразу при включении, а не при первом нажатии:
                # многие игры ищут контроллеры только при запуске или в меню.
                if ev[1] and self._has_pad:
                    self._pad.apply(self._engine.pad_state)
            elif ev[0] == "pad":
                self._pad.apply(ev[1])
        sendinput.apply(events)

    def _pump(self) -> bool:
        """События SDL: отметить сдвинутые оси; True - устройства подключили или отключили."""
        changed, moved = self._input.poll()
        for instance_id, axis in moved:
            self._mark_known(instance_id, axis)
        return changed

    def _rebuild(self) -> None:
        sdl = self._input.sdl
        joys, infos, seen = [], [], {}
        for j in self._input.scan():
            try:
                if self._own_slot is not None and player_index(sdl, j) == self._own_slot:
                    log.info("skip own virtual gamepad: %s (XInput slot %s)", j.get_name(), self._own_slot)
                    continue
                guid = j.get_guid()
                seen[guid] = seen.get(guid, 0) + 1
                key = guid if seen[guid] == 1 else f"{guid}#{seen[guid]}"
                joys.append((key, j))
                infos.append(DeviceInfo(key, j.get_name(), j.get_numaxes(), j.get_numbuttons(), j.get_numhats()))
            except Exception:  # noqa: BLE001
                log.exception("joystick %s init failed", j.get_instance_id())
        self._joys = joys
        self._known = {k: set() for k, _ in joys}
        # Вибрируем первым устройством с вибромотором (обычно это и есть руль). Сначала
        # вибромотор отпускает отключённый руль, потом закрываются лишние джойстики:
        # haptic не должен пережить свой джойстик.
        attached = self._haptic.attach(sdl, [j for _, j in joys])
        self._input.keep([j for _, j in joys])
        if attached:
            status = f"вибрирует: {self._haptic.name}"
        else:
            status = "у руля нет вибромотора" if joys else "руль не подключён"
        self.rumble_status = status
        self.events.put(("rumble_status", status))
        with self._lock:
            self._infos = infos
        self.events.put(("devices", infos))
        log.info("devices: %s", [(d.name, d.axes, d.buttons, d.hats) for d in infos])

    def _mark_known(self, instance_id: int, axis: int) -> None:
        for key, j in self._joys:
            if j.get_instance_id() == instance_id:
                self._known.setdefault(key, set()).add(axis)

    def _read(self) -> dict[str, DeviceState]:
        states: dict[str, DeviceState] = {}
        for key, j in self._joys:
            known = self._known.setdefault(key, set())
            axes = []
            for a in range(j.get_numaxes()):
                v = j.get_axis(a)
                if v != 0.0:
                    known.add(a)
                axes.append(v if a in known else None)
            buttons = tuple(bool(j.get_button(b)) for b in range(j.get_numbuttons()))
            hats = tuple(tuple(j.get_hat(h)) for h in range(j.get_numhats()))
            states[key] = DeviceState(tuple(axes), buttons, hats)
        return states
