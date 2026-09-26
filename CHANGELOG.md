# Changelog

## 3.2.0 - 2026-09-26

- The wheel is read without pygame. The input layer talks to SDL through PySDL2, and `SDL2.dll` comes from `pysdl2-dll`, pinned to SDL 2.28.4 - the version pygame 2.6.1 shipped. Device GUIDs, axes, buttons, the hat, hot-plugging, rumble and the virtual gamepad behave exactly as before; existing `config.json` bindings keep working.
- `WheelScript.exe --selftest [file]`: runs the input service without a window for 2 seconds and writes SDL version, loaded `SDL2.dll`, devices and errors into a file. Presses nothing, does not rumble.
- The build bundles only `SDL2.dll` (not the whole pygame set of image, audio and font libraries), checks that pygame did not get in and runs the selftest of the built exe. The portable archive is 1.7 MB smaller.
- Tests: 248 (+43), including the input layer against a stand-in for SDL and against the real SDL with a virtual wheel.

---

## 3.2.0 - 2026-09-26

- Руль читается без pygame. Слой ввода работает с SDL через PySDL2, `SDL2.dll` берётся из `pysdl2-dll` и закреплена на SDL 2.28.4 — той же версии, что была у pygame 2.6.1. GUID устройств, оси, кнопки, крестовина, горячее подключение, вибрация и виртуальный геймпад работают как раньше; привязки в `config.json` находят свои устройства.
- `WheelScript.exe --selftest [файл]`: сервис ввода без окна на 2 секунды, в файл пишутся версия SDL, загруженная `SDL2.dll`, устройства и ошибки. Ничего не нажимает, руль не трясёт.
- В сборку кладётся только `SDL2.dll` (без библиотек картинок, звука и шрифтов, которые тянул pygame); сборка проверяет, что pygame в неё не попал, и прогоняет самопроверку собранного exe. Портативный архив стал меньше на 1,7 МБ.
- Тестов 248 (+43), среди них слой ввода с подделкой SDL и с настоящей SDL и виртуальным рулём.
