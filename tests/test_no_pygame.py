"""pygame в проекте больше не используется: ни в коде, ни в зависимостях, ни в сборке."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPORT = re.compile(r"^\s*(?:import|from)\s+pygame\b|__import__\(\s*['\"]pygame|import_module\(\s*['\"]pygame",
                    re.MULTILINE)


def sources():
    for folder in ("wheelscript", "tools", "tests"):
        yield from (ROOT / folder).rglob("*.py")
    yield ROOT / "run.py"


def test_no_pygame_import_in_sources():
    found = [str(p.relative_to(ROOT)) for p in sources() if IMPORT.search(p.read_text(encoding="utf-8"))]
    assert found == []


def test_no_pygame_in_dependencies():
    for name in ("requirements.txt", "requirements-dev.txt", "pyproject.toml"):
        text = (ROOT / name).read_text(encoding="utf-8").lower()
        assert "pygame" not in text, name
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^pysdl2==", req, re.MULTILINE) and re.search(r"^pysdl2-dll==2\.28\.4$", req, re.MULTILINE), \
        "SDL закреплена на той же версии, что была у pygame"


def test_build_bundles_sdl_and_never_pygame():
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    assert "--exclude-module pygame" in build, "старая .venv с pygame не протащит его в сборку"
    assert not re.search(r"(collect-\w+|hidden-import|add-data|add-binary)[^\n]*pygame", build, re.IGNORECASE)
    assert re.search(r"_internal\\pygame\"\) \{ throw", build), "сборка проверяет, что pygame в неё не попал"
    assert re.search(r"--add-binary \"\$sdlDll;sdl2dll/dll\"", build), "SDL2.dll кладётся туда, где её ищет sdl2dll"
    assert re.search(r"_internal\\sdl2dll\\dll\\SDL2\.dll\"\)\) \{ throw", build), "и сборка проверяет, что она там"
    assert "--selftest" in build


def test_program_modules_do_not_load_pygame():
    code = ("import sys; import wheelscript.app, wheelscript.service, wheelscript.rumble, "
            "wheelscript.sdlinput, wheelscript.selftest; "
            "from wheelscript import sdlinput; sdlinput.load(); "
            "print('pygame' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"
