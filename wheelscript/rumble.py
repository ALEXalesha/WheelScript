"""
Вибрация из игры на руль.

Игра вибрирует виртуальным геймпадом Xbox, драйвер ViGEmBus сообщает силу двух
моторов (0…255) из своего потока. RumbleRelay запоминает последнее значение, а поток
сервиса раз в тик спрашивает у него, что сказать рулю. Одна команда на руле живёт
PLAY_MS, поэтому, пока вибрация нужна, она повторяется раньше, чем истечёт: если
WheelScript зависнет или упадёт, руль сам затихнет.

Руль трясём через SDL haptic той же SDL, что читает руль (модуль sdl2 из sdlinput):
SDL_JoystickRumble у PXN V9 не работает (pygame через него возвращал False), а
SDL_HapticRumblePlay работает.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

log = logging.getLogger(__name__)

PLAY_MS = 400      # сколько живёт одна команда на руле
REFRESH = 0.2      # повторять не реже: при тике до 0.1 с эффект не успевает истечь
STEP = 0.02        # меньшие изменения силы не шлём; ниже STEP — тишина
SMALL_WEIGHT = 0.6
TEST_SECONDS = 0.5

Command = tuple    # ("play", сила 0…1, мс) | ("stop",)


def _clamp01(x: float) -> float:
    return 0.0 if not x > 0 else 1.0 if x > 1 else float(x)  # NaN -> 0


def level_of(large: int, small: int) -> float:
    """Сила 0…1 из двух моторов Xbox. У руля один вибромотор, поэтому берём сильнейший;
    маленький мотор в играх — лёгкое «жужжание», ему вес поменьше."""
    return _clamp01(max(large, SMALL_WEIGHT * small) / 255)


class RumbleRelay:
    """Чистая логика без SDL: что и когда отправить рулю."""

    def __init__(self) -> None:
        self._game = (0, 0)
        self._level = 0.0            # что сейчас играет на руле (0 — тишина)
        self._sent_at = -math.inf
        self._test_until = -math.inf
        self._test_level = 0.0

    @property
    def level(self) -> float:
        return self._level

    @property
    def sent_at(self) -> float:
        return self._sent_at

    def set_game(self, large: int, small: int) -> None:
        """Вызывается из потока ViGEm: присваивание кортежа атомарно под GIL."""
        self._game = (max(0, min(255, int(large))), max(0, min(255, int(small))))

    def reset(self) -> None:
        self._game = (0, 0)

    def test(self, now: float, strength: float) -> None:
        self._test_until = now + TEST_SECONDS
        self._test_level = _clamp01(strength)

    def target(self, now: float, active: bool, strength: float) -> float:
        if now < self._test_until:
            return self._test_level
        if not active:
            return 0.0
        return _clamp01(level_of(*self._game) * _clamp01(strength))

    def tick(self, now: float, active: bool, strength: float) -> Optional[Command]:
        want = self.target(now, active, strength)
        if want < STEP:
            if self._level > 0:
                self._level = 0.0
                return ("stop",)
            return None
        if abs(want - self._level) >= STEP or now - self._sent_at >= REFRESH:
            self._level, self._sent_at = want, now
            return ("play", want, PLAY_MS)
        return None


SDL_INIT_HAPTIC = 0x1000


def _instance_id(joystick) -> Optional[int]:
    try:
        return joystick.get_instance_id()
    except Exception:  # noqa: BLE001
        return None


def player_index(sdl, joystick) -> Optional[int]:
    """Слот XInput устройства (0…3) или None. По нему сервис узнаёт свой виртуальный геймпад."""
    try:
        sj = sdl.SDL_JoystickFromInstanceID(joystick.get_instance_id())
        i = sdl.SDL_JoystickGetPlayerIndex(sj) if sj else -1
    except Exception:  # noqa: BLE001
        return None
    return i if i >= 0 else None


class WheelHaptic:
    """Вибромотор руля. Любая ошибка глушится: вибрация не должна мешать маппингу."""

    def __init__(self) -> None:
        self._sdl = None
        self._h = None
        self._warned = False
        self.name = ""
        self.instance_id: Optional[int] = None

    @property
    def available(self) -> bool:
        return self._h is not None

    def attach(self, sdl, joysticks) -> bool:
        """Вибрировать первым устройством с вибромотором. Уже открытый мотор не трогаем,
        пока его устройство на месте: SDL (DirectInput) не может заново открыть haptic
        у джойстика, который всё ещё открыт, — после close() руль терял бы вибрацию."""
        if self.available and self.instance_id in {_instance_id(j) for j in joysticks}:
            return True
        self.close()
        return any(self.open(sdl, j) for j in joysticks)

    def open(self, sdl, joystick) -> bool:
        self.close()
        try:
            if not sdl.SDL_WasInit(SDL_INIT_HAPTIC) and sdl.SDL_InitSubSystem(SDL_INIT_HAPTIC) != 0:
                return False
            sj = sdl.SDL_JoystickFromInstanceID(joystick.get_instance_id())
            if not sj or sdl.SDL_JoystickIsHaptic(sj) != 1:
                return False
            h = sdl.SDL_HapticOpenFromJoystick(sj)
            if not h:
                return False
            if sdl.SDL_HapticRumbleSupported(h) != 1 or sdl.SDL_HapticRumbleInit(h) != 0:
                sdl.SDL_HapticClose(h)
                return False
        except Exception:  # noqa: BLE001
            log.exception("haptic open failed")
            return False
        self._sdl, self._h, self._warned, self.name = sdl, h, False, joystick.get_name()
        self.instance_id = _instance_id(joystick)
        log.info("rumble: %s", self.name)
        return True

    def apply(self, cmd: Command) -> None:
        if self._h is None:
            return
        try:
            if cmd[0] == "play":
                if self._sdl.SDL_HapticRumblePlay(self._h, float(cmd[1]), int(cmd[2])) != 0 and not self._warned:
                    self._warned = True
                    log.warning("rumble play failed: %s", self._sdl.SDL_GetError())
            else:
                self._sdl.SDL_HapticRumbleStop(self._h)
        except Exception:  # noqa: BLE001
            log.exception("rumble failed")

    def close(self) -> None:
        h, self._h = self._h, None
        self.instance_id = None
        if h is None:
            return
        try:
            self._sdl.SDL_HapticRumbleStop(h)
            self._sdl.SDL_HapticClose(h)
        except Exception:  # noqa: BLE001
            log.exception("haptic close failed")
