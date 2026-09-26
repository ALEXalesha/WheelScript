"""Инварианты передачи вибрации из игры на руль (без настоящего SDL)."""

from hypothesis import given
from hypothesis import strategies as st

from wheelscript import rumble
from wheelscript.rumble import PLAY_MS, REFRESH, STEP, RumbleRelay, WheelHaptic, level_of

any_float = st.floats(allow_nan=True, allow_infinity=True)
motor = st.integers(-50, 400)
ops = st.lists(st.one_of(
    st.tuples(st.just("game"), motor, motor),
    st.tuples(st.just("tick"), st.floats(0, 0.1), st.booleans(), st.one_of(any_float, st.floats(0, 1))),
    st.tuples(st.just("test"), st.one_of(any_float, st.floats(0, 1))),
    st.tuples(st.just("reset")),
), max_size=80)


@given(motor, motor)
def test_level_in_range_and_large_dominates(large, small):
    v = level_of(max(0, min(255, large)), max(0, min(255, small)))
    assert 0.0 <= v <= 1.0
    assert level_of(255, small if 0 <= small <= 255 else 0) == 1.0
    assert level_of(0, 0) == 0.0


@given(ops)
def test_relay_invariants(seq):
    r = RumbleRelay()
    now = 0.0
    playing = False          # что сейчас делает руль по мнению «руля»
    expires = -1.0
    for op in seq:
        if op[0] == "game":
            r.set_game(op[1], op[2])
        elif op[0] == "reset":
            r.reset()
        elif op[0] == "test":
            r.test(now, op[1])
        else:
            _, dt, active, strength = op
            now += dt
            want = r.target(now, active, strength)
            assert 0.0 <= want <= 1.0
            cmd = r.tick(now, active, strength)
            if cmd is not None and cmd[0] == "play":
                assert STEP <= cmd[1] <= 1.0 and cmd[2] == PLAY_MS
                playing, expires = True, now + PLAY_MS / 1000
            elif cmd is not None:
                assert cmd == ("stop",)
                assert playing, "stop без play — лишняя команда"
                playing = False
            if want < STEP:
                assert not playing and r.level == 0.0, "игра затихла или маппинг выключен — руль тоже молчит"
            else:
                assert playing and abs(r.level - want) < STEP, "руль отстаёт от игры не больше чем на STEP"
                assert expires - now > PLAY_MS / 1000 - REFRESH - 1e-9, "эффект не истекает до следующего тика"


@given(st.lists(st.tuples(motor, motor), max_size=20), st.floats(0, 0.1))
def test_zero_strength_never_vibrates(games, dt):
    r = RumbleRelay()
    now = 0.0
    for g in games:
        r.set_game(*g)
        now += dt
        assert r.tick(now, True, 0.0) is None


def test_inactive_stops_once_and_test_pulse_works():
    r = RumbleRelay()
    r.set_game(255, 0)
    assert r.tick(0.0, True, 1.0) == ("play", 1.0, PLAY_MS)
    assert r.tick(0.05, False, 1.0) == ("stop",)
    assert r.tick(0.10, False, 1.0) is None
    r.test(0.2, 0.5)
    assert r.tick(0.25, False, 1.0) == ("play", 0.5, PLAY_MS)
    assert r.tick(2.0, False, 1.0) == ("stop",)


class FakeSDL:
    def __init__(self):
        self.calls = []

    def SDL_HapticRumblePlay(self, h, level, ms):  # noqa: N802
        self.calls.append(("play", h, level, ms))
        return 0

    def SDL_HapticRumbleStop(self, h):  # noqa: N802
        self.calls.append(("stop", h))

    def SDL_HapticClose(self, h):  # noqa: N802
        self.calls.append(("close", h))


def test_haptic_without_device_is_noop():
    h = WheelHaptic()
    h.apply(("play", 1.0, PLAY_MS))
    h.close()
    assert not h.available


def test_haptic_commands_and_close():
    h = WheelHaptic()
    h._sdl, h._h = FakeSDL(), 7
    h.apply(("play", 0.5, PLAY_MS))
    h.apply(("stop",))
    sdl = h._sdl
    h.close()
    assert sdl.calls == [("play", 7, 0.5, PLAY_MS), ("stop", 7), ("stop", 7), ("close", 7)]
    assert not h.available
    h.close()
    assert len(sdl.calls) == 4, "повторное закрытие ничего не делает"


class QuirkySDL:
    """Как SDL 2.28 + DirectInput у PXN V9: закрытый haptic нельзя снова открыть
    у джойстика, который всё ещё открыт (SDL_SYS_HapticOpenFromJoystick failed)."""

    def __init__(self):
        self.opens, self.closed = [], set()

    def SDL_WasInit(self, f): return f  # noqa: E704,N802
    def SDL_InitSubSystem(self, f): return 0  # noqa: E704,N802
    def SDL_JoystickFromInstanceID(self, iid): return 100 + iid  # noqa: E704,N802
    def SDL_JoystickIsHaptic(self, sj): return 1  # noqa: E704,N802
    def SDL_HapticRumbleSupported(self, h): return 1  # noqa: E704,N802
    def SDL_HapticRumbleInit(self, h): return 0  # noqa: E704,N802
    def SDL_HapticRumbleStop(self, h): pass  # noqa: E704,N802
    def SDL_HapticClose(self, h): self.closed.add(h)  # noqa: E704,N802

    def SDL_HapticOpenFromJoystick(self, sj):  # noqa: N802
        if sj in self.closed:
            return None
        self.opens.append(sj)
        return sj


class FakeJoy:
    def __init__(self, iid):
        self.iid = iid

    def get_instance_id(self):
        return self.iid

    def get_name(self):
        return "V9GEN2"


def test_attach_keeps_haptic_across_rebuilds():
    """Регрессия: при старте SDL шлёт JOYDEVICEADDED, сервис перестраивает список
    устройств, и переоткрытие haptic молча выключало вибрацию."""
    sdl = QuirkySDL()
    h = WheelHaptic()
    assert h.attach(sdl, [FakeJoy(0)])
    assert h.attach(sdl, [FakeJoy(0)]), "тот же руль после rebuild — вибрация остаётся"
    assert sdl.opens == [100] and h.available
    assert h.attach(sdl, [FakeJoy(3)]), "руль переподключили — открываем заново"
    assert sdl.opens == [100, 103] and 100 in sdl.closed and h.instance_id == 3
    assert not h.attach(sdl, [])
    assert not h.available and 103 in sdl.closed and h.instance_id is None


class SlotSDL:
    def __init__(self, slots):
        self.slots = slots

    def SDL_JoystickFromInstanceID(self, iid): return ("joy", iid) if iid in self.slots else None  # noqa: E704,N802
    def SDL_JoystickGetPlayerIndex(self, sj): return self.slots[sj[1]]  # noqa: E704,N802


def test_player_index_is_xinput_slot_or_none():
    """По слоту сервис узнаёт свой виртуальный геймпад и не читает собственный выход как ввод."""
    sdl = SlotSDL({0: 2, 1: -1})
    assert rumble.player_index(sdl, FakeJoy(0)) == 2
    assert rumble.player_index(sdl, FakeJoy(1)) is None, "-1 у SDL - слота нет"
    assert rumble.player_index(sdl, FakeJoy(7)) is None, "не открыт - не наш"
    assert rumble.player_index(None, FakeJoy(0)) is None, "ошибка SDL не роняет перестройку списка"
