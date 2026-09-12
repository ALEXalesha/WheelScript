"""Stateful-проверка: hypothesis сам придумывает последовательности действий с движком."""

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from wheelscript.engine import Engine

from .strategies import DEV, FakeOS, profiles, states, weird_dts


class EngineMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.engine = Engine(enabled=False)
        self.os = FakeOS()
        self.last_states = {}

    @rule(p=profiles())
    def load_profile(self, p):
        self.os.apply(self.engine.set_profile(p))
        assert self.os.keys == set()

    @rule(p=profiles(), s=states())
    def load_profile_while_holding(self, p, s):
        self.os.apply(self.engine.set_profile(p, s, DEV))

    @rule(s=states(), dt=weird_dts, default=st.sampled_from([DEV, None]))
    def step(self, s, dt, default):
        self.last_states = s
        self.os.apply(self.engine.step(s, dt, default))

    @rule(s=states(), n=st.integers(1, 10))
    def hold_same_state(self, s, n):
        for _ in range(n):
            self.os.apply(self.engine.step(s, 0.016, DEV))

    @rule(flag=st.booleans())
    def set_enabled(self, flag):
        self.os.apply(self.engine.set_enabled(flag))
        assert self.engine.enabled == flag

    @rule()
    def release_all(self):
        self.os.apply(self.engine.release_all())
        assert self.os.keys == set() and self.os.buttons == set()

    @precondition(lambda self: self.last_states)
    @rule()
    def suspend_resume(self):
        self.os.apply(self.engine.release_all())
        self.engine.block_active(self.last_states, DEV)
        self.os.apply(self.engine.step(self.last_states, 0.016, DEV))
        assert self.os.keys == set() and self.os.buttons == set(), "после паузы зажатое на руле не должно нажиматься"

    @invariant()
    def os_matches_engine(self):
        assert self.os.keys == self.engine.held_keys()
        assert self.os.buttons == self.engine.held_buttons()

    @invariant()
    def disabled_holds_nothing(self):
        if not self.engine.enabled:
            assert self.os.keys == set() and self.os.buttons == set()

    def teardown(self):
        self.os.apply(self.engine.release_all())
        assert self.os.keys == set() and self.os.buttons == set()


EngineMachine.TestCase.settings = settings(max_examples=200, stateful_step_count=40, deadline=None)
TestEngineMachine = EngineMachine.TestCase
