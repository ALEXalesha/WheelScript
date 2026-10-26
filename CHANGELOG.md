# Changelog

## 3.2.1 - 2026-10-25

- The menu buttons "+ Add" and "Profile actions" show their own arrow ▾ next to the text instead of the tiny Fusion indicator under it.
- Table columns get their width by content: "Name" is no longer cut while "Parameters" has room to spare; when not everything fits, columns shrink in proportion to what they lack, without horizontal scrolling.
- The gamepad and rumble status at the bottom uses the normal text colour instead of the pale hint colour.
- Hyphens instead of long dashes in all texts.
- Tests: 254 (+6): column widths as a property test, menu arrows, status colour, no long dashes.

## 3.2.0 - 2026-09-26

- The wheel is read without pygame. The input layer talks to SDL through PySDL2, and `SDL2.dll` comes from `pysdl2-dll`, pinned to SDL 2.28.4 - the version pygame 2.6.1 shipped. Device GUIDs, axes, buttons, the hat, hot-plugging, rumble and the virtual gamepad behave exactly as before; existing `config.json` bindings keep working.
- `WheelScript.exe --selftest [file]`: runs the input service without a window for 2 seconds and writes SDL version, loaded `SDL2.dll`, devices and errors into a file. Presses nothing, does not rumble.
- The build bundles only `SDL2.dll` (not the whole pygame set of image, audio and font libraries), checks that pygame did not get in and runs the selftest of the built exe. The portable archive is 1.7 MB smaller.
- Tests: 248 (+43), including the input layer against a stand-in for SDL and against the real SDL with a virtual wheel.

## 3.1.0 - 2026-09-25

The place, size and maximized state are written to `window.json` next to `config.json` when the window closes, and put back at the next start. If that monitor is gone or the title bar would land off every screen, the window opens at the default size in the middle instead. A broken `window.json` never touches the settings: it is a separate file, so it cannot send `config.json` to `config.broken-*.json`.

The ViGEmBus driver for the virtual gamepad is installed separately, as before. 205 tests green.

## 3.0.1 - 2026-09-23

The shortcut used to be written through `WScript.Shell`, which saves `.lnk` files through the ANSI code page. With letters outside that code page in the path (Cyrillic on an English Windows, CJK on a Russian one) the shortcut was not created at all, and the PowerShell error text lost the same letters to the OEM code page on the way to the window. It was found by CI on the GitHub runner, which runs an English Windows: the CI of this repository had been red since the first publication. The shortcut is now written through `IShellLinkW`, the script goes to PowerShell as `-EncodedCommand`, and errors come back in UTF-8. The tests use Japanese letters, which exist in no Russian Windows code page, so they fail without the fix on a Russian machine too.

The ViGEmBus driver for the virtual gamepad is installed separately, as before. 196 tests green, locally and in CI.

## 3.0.0 - 2026-09-22

The interface was rewritten from Tkinter to Qt (PySide6).

**Why:** Tk lagged noticeably while the window was being resized on Windows, and the dark theme had to be assembled widget by widget. Qt draws the window as one thing and follows the system light/dark setting.

**What the program does:** maps a racing wheel, its pedals, buttons and shifter to mouse, keyboard or a virtual Xbox 360 gamepad, for games that do not understand a wheel. Bindings are made by clicking the input field and then moving the thing you want to bind - the program recognises the axis, button or hat by itself, and guesses whether an axis is a pedal.

---

## 3.2.1 - 2026-10-25

- У кнопок «+ Добавить» и «Действия с профилем» своя стрелка ▾ рядом с текстом вместо крошечного значка Fusion под ним.
- Ширина колонок таблицы - по содержимому: «Название» больше не обрезается, а «Параметры» не держат лишнего места; если всё не влезает, колонки ужимаются пропорционально, по-прежнему без горизонтальной прокрутки.
- Состояние геймпада и вибрации внизу - обычным цветом текста, а не бледным.
- Дефис вместо длинного тире во всех текстах.
- Тестов 254 (+6): ширина колонок как закон, стрелки меню, цвет состояния, нет длинного тире.

## 3.2.0 - 2026-09-26

- Руль читается без pygame. Слой ввода работает с SDL через PySDL2, `SDL2.dll` берётся из `pysdl2-dll` и закреплена на SDL 2.28.4 - той же версии, что была у pygame 2.6.1. GUID устройств, оси, кнопки, крестовина, горячее подключение, вибрация и виртуальный геймпад работают как раньше; привязки в `config.json` находят свои устройства.
- `WheelScript.exe --selftest [файл]`: сервис ввода без окна на 2 секунды, в файл пишутся версия SDL, загруженная `SDL2.dll`, устройства и ошибки. Ничего не нажимает, руль не трясёт.
- В сборку кладётся только `SDL2.dll` (без библиотек картинок, звука и шрифтов, которые тянул pygame); сборка проверяет, что pygame в неё не попал, и прогоняет самопроверку собранного exe. Портативный архив стал меньше на 1,7 МБ.
- Тестов 248 (+43), среди них слой ввода с подделкой SDL и с настоящей SDL и виртуальным рулём.

## 3.1.0 - 2026-09-25

Место, размер и развёрнутость окна при закрытии пишутся в `window.json` рядом с `config.json` и возвращаются при следующем запуске. Если того монитора больше нет или заголовок окна оказался бы за пределами всех экранов, окно открывается обычного размера посередине. Испорченный `window.json` не трогает настройки: это отдельный файл, и он не может отправить `config.json` в `config.broken-*.json`.

Драйвер ViGEmBus для виртуального геймпада, как и раньше, ставится отдельно. Тестов 205, все зелёные.

## 3.0.1 - 2026-09-23

Ярлык раньше записывался через `WScript.Shell`, который сохраняет `.lnk` в кодовой странице ANSI. Если в пути были буквы вне этой кодовой страницы (кириллица на английской Windows, иероглифы на русской), ярлык не создавался вовсе, а текст ошибки PowerShell терял те же буквы в кодовой странице OEM по дороге к окну. Нашёл это CI на раннере GitHub с английской Windows: CI этого репозитория был красным с первой публикации. Теперь ярлык пишется через `IShellLinkW`, скрипт уходит в PowerShell как `-EncodedCommand`, а ошибки возвращаются в UTF-8. Тесты используют японские буквы, которых нет ни в одной кодовой странице русской Windows, поэтому без исправления они падают и на русской машине.

Драйвер ViGEmBus для виртуального геймпада, как и раньше, ставится отдельно. Тестов 196, зелёные локально и в CI.

## 3.0.0 - 2026-09-22

Интерфейс переписан с Tkinter на Qt (PySide6).

**Зачем:** Tk заметно тормозил при изменении размера окна на Windows, а тёмную тему приходилось собирать по виджету. Qt рисует окно целиком и следует системной светлой или тёмной теме.

**Что делает программа:** переводит руль, педали, кнопки и коробку передач в мышь, клавиатуру или виртуальный геймпад Xbox 360 - для игр, которые руль не понимают. Привязка делается так: щёлкнуть по полю ввода и подвигать то, что нужно привязать; программа сама узнаёт ось, кнопку или крестовину и догадывается, педаль ли это.
