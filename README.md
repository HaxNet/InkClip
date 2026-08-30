# InkClip

A fast, lightweight scratchpad drawing app for Linux.

Open it, scribble something on a blank white canvas, press <kbd>Ctrl</kbd>+<kbd>C</kbd>,
and paste the drawing straight into chat, a doc, or a bug report. No accounts, no
files to manage, no Electron — just Python and Qt.

## Screenshot

<!-- Drop a screenshot at docs/screenshot.png and it will show up here. -->

![InkClip window](docs/screenshot.png)

## Features

- Blank white canvas with antialiased freehand drawing
- Pen, highlighter, eraser, and rectangular select tools
- Copy a selected region, or just the drawing itself, instead of the whole canvas
- Delete a selected region, leaving the rest of the drawing alone
- Canvas size presets (fit to window, 800x600, 1280x720, 1920x1080) plus a custom size
- Six colors: black, red, blue, green, yellow, purple
- Four brush sizes: small, medium, large, extra large
- Copy the canvas to the system clipboard as an image
- Save the canvas as a PNG
- Undo (up to 30 steps) and clear
- Stylus/tablet input with pressure-sensitive pen strokes when Qt reports it
- Resizing the window or the canvas keeps your drawing intact

## Install (Arch Linux)

```bash
sudo pacman -S python pyside6
```

> The Arch package is called `pyside6` (repo: `extra`). It used to be published as
> `python-pyside6`; that name no longer resolves, so `pacman -S python-pyside6`
> will fail with "target not found".

On Wayland compositors, also install the Qt Wayland platform plugin:

```bash
sudo pacman -S qt6-wayland
```

### Or with a virtualenv

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Install as a desktop app (rofi, wofi, app menus)

To get an InkClip entry with an icon in `rofi -show drun` and any other launcher,
install it so it lands in the XDG data dirs.

### Per user, no root (recommended)

```bash
make user-install
```

Installs into `~/.local`:

| Path | What |
| --- | --- |
| `~/.local/bin/inkclip` | launcher script |
| `~/.local/share/inkclip/main.py` | the app |
| `~/.local/share/applications/inkclip.desktop` | the launcher entry |
| `~/.local/share/icons/hicolor/scalable/apps/inkclip.svg` | the icon |

The entry shows up in rofi right away — no logout, no relogin. Search for
`inkclip`, or any of its keywords: *draw*, *sketch*, *scratchpad*, *clipboard*.

Remove it again with:

```bash
make user-uninstall
```

### System-wide

```bash
sudo make install              # into /usr/local
sudo make install PREFIX=/usr  # into /usr
sudo make uninstall
```

### As a real pacman package (yay / makepkg)

A `PKGBUILD` is included, so InkClip can be installed and removed like any other
Arch package — pacman owns the files and `pacman -R` cleans them up properly:

```bash
makepkg -si          # build and install from this checkout
pacman -Qo $(command -v inkclip)   # confirm pacman owns it
sudo pacman -R inkclip             # uninstall
```

`yay -U inkclip-*.pkg.tar.zst` works too if you would rather install the built
package through your AUR helper. The `PKGBUILD` has a commented-out block showing
what to change to publish it on the AUR from a tagged release tarball.

## Run

From a checkout:

```bash
python main.py     # or: make run
```

Once installed (see above), from anywhere:

```bash
inkclip
```

...or just pick **InkClip** out of rofi.

## Copying just the drawing

<kbd>Ctrl</kbd>+<kbd>A</kbd> selects the drawing rather than the canvas: InkClip
finds the bounding box of every non-white pixel and selects that, with a few
pixels of breathing room. Press <kbd>Ctrl</kbd>+<kbd>C</kbd> and you get a tightly
cropped image instead of your sketch adrift in a sea of white.

```text
draw something  ->  Ctrl+A  ->  Ctrl+C  ->  paste
```

It stays on whatever tool you were using, so you can keep drawing and hit
<kbd>Ctrl</kbd>+<kbd>A</kbd> again for an updated crop. Erasing shrinks the box
back down, and on a blank canvas it just says so instead of selecting nothing.

<kbd>Del</kbd> (or <kbd>Backspace</kbd>) erases what is inside the selection, so
<kbd>Ctrl</kbd>+<kbd>A</kbd> then <kbd>Del</kbd> wipes the drawing. It is undoable
with <kbd>Ctrl</kbd>+<kbd>Z</kbd> like any other edit.

<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>A</kbd> selects the entire canvas, blank
margins included, if you actually want the full frame.

## Selecting part of a drawing

To grab one specific piece instead:

1. Pick **Select** in the toolbar (or press <kbd>S</kbd>)
2. Drag a rectangle over the part you want
3. <kbd>Ctrl</kbd>+<kbd>C</kbd>

Copy and Save PNG both act on the selection whenever one is active, so you can
pull a single diagram out of a busy canvas without cropping it afterwards.

- <kbd>Del</kbd> / <kbd>Backspace</kbd> erases the selected region only, leaving
  the rest of the drawing untouched
- <kbd>Esc</kbd> (or a single click with the select tool) dismisses the marquee
  without changing the drawing
- The status bar always shows the active selection, so you never copy a stale one
- Deleting a region drops the marquee with it, so a later <kbd>Ctrl</kbd>+<kbd>C</kbd>
  cannot silently copy an emptied region

The selection only controls what gets copied and saved; it does not restrict where
you can draw. Picking a color or another tool leaves select mode.

## Canvas size

The **Canvas** toolbar menu sets how big the drawing area is:

| Choice | Behaviour |
| --- | --- |
| Fit to window | The canvas fills the window and grows as you resize it (the default) |
| 800 x 600, 1280 x 720, 1920 x 1080 | A fixed canvas of exactly that many pixels |
| Custom... | Any size from 64x64 up to 8192x8192 |

A fixed canvas is centred in the window and scrolls if it is larger than the
window. Its size is exact: a 1920x1080 canvas copies and saves as a 1920x1080
image, which is handy when a drawing needs to match a specific slot.

Changing the canvas size keeps whatever you have already drawn, and undo keeps
working across the change.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| <kbd>Ctrl</kbd>+<kbd>C</kbd> | Copy canvas (or selection) to clipboard |
| <kbd>Ctrl</kbd>+<kbd>A</kbd> | Select just the drawing (trims the blank margins) |
| <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>A</kbd> | Select the whole canvas |
| <kbd>Del</kbd> / <kbd>Backspace</kbd> | Erase the selected region |
| <kbd>Esc</kbd> | Dismiss the selection |
| <kbd>Ctrl</kbd>+<kbd>Z</kbd> | Undo |
| <kbd>Ctrl</kbd>+<kbd>S</kbd> | Save canvas (or selection) as PNG |
| <kbd>P</kbd> | Pen |
| <kbd>H</kbd> | Highlighter |
| <kbd>E</kbd> | Eraser |
| <kbd>S</kbd> | Select |
| <kbd>C</kbd> | Clear the whole canvas |
| <kbd>1</kbd> / <kbd>2</kbd> / <kbd>3</kbd> / <kbd>4</kbd> | Small / medium / large / extra large brush (`S` `M` `L` `XL` on the toolbar) |

Plain <kbd>C</kbd> clears the canvas and <kbd>Ctrl</kbd>+<kbd>C</kbd> copies it — Qt
matches modifiers exactly, so the two never collide.

## Development notes

```text
InkClip/
├── main.py                       # the whole app
├── Makefile                      # install / uninstall targets
├── PKGBUILD                      # Arch package definition
├── packaging/
│   ├── inkclip.desktop.in        # launcher entry (@BINDIR@ filled in at install)
│   └── inkclip.svg               # scalable icon
├── requirements.txt
└── README.md
```

The app itself is still one file, split into two classes:

- **`DrawingCanvas(QWidget)`** — owns a `QImage` that strokes are painted onto, so
  the drawing survives repaints. Pen and eraser strokes go straight onto that
  image; the eraser is simply a white pen. Highlighter strokes are collected on a
  transparent overlay image and composited at 35% opacity when the stroke ends,
  which keeps a self-crossing stroke evenly translucent instead of stacking into a
  solid line.
- **`MainWindow(QMainWindow)`** — toolbar, status bar, shortcuts, clipboard, and
  save-file handling. The canvas lives in a `QScrollArea` so a canvas bigger than
  the window stays reachable.
- **`CanvasSizeDialog(QDialog)`** — two spin boxes behind **Canvas > Custom...**.

Other things worth knowing:

- The backing image is allocated at the widget size times the device pixel ratio,
  so strokes stay crisp on HiDPI screens and copied images come out at full
  resolution. A *fixed* canvas is the exception: it is defined in output pixels and
  stays at a ratio of 1.0, because "1920x1080" has to mean 1920x1080 in the
  clipboard. See `DrawingCanvas._image_dpr`.
- The selection is a plain `QRect` in canvas coordinates. `canvas_image(region)`
  converts it to backing-image pixels and crops, which is all copy and save need.
  A drag builds the rect from its own width and height rather than via
  `QRect(topLeft, bottomRight)`, whose inclusive corners would make a 300px drag
  select 301px.
- Marching ants are a white line with a dashed dark line drawn over it, with the
  dash offset advanced by a `QTimer` only while a selection exists.
- `DrawingCanvas.content_rect` finds the drawn area by scanning the raw image
  buffer instead of calling `pixel()` millions of times. A white pixel is always
  four `0xff` bytes, so an untouched row compares equal to a run of `0xff`, and
  stripping that run off each end of a row gives the first and last touched pixel
  in it. A full 1920x1080 canvas scans in about 6 ms, a blank one in under 1 ms.
  `CONTENT_MARGIN` controls the breathing room left around the result.
- `resizeEvent` only ever grows the backing image, so making the window bigger
  reveals more white canvas and making it smaller does not destroy anything.
- Undo pushes a full image copy before each stroke, capped at 30 states
  (`UNDO_LIMIT`). Simple, and plenty fast for a scratchpad.
- Tunables sit at the top of the file: `BRUSH_SIZES`, `PALETTE`,
  `HIGHLIGHTER_OPACITY`, `HIGHLIGHTER_WIDTH_FACTOR`, `ERASER_WIDTH_FACTOR`.
- `app.setDesktopFileName("inkclip")` links the window to `inkclip.desktop`, which
  is what lets compositors and bars (niri, waybar, ...) show the right name and
  icon for a running InkClip window.
- The `.desktop` entry is generated from `packaging/inkclip.desktop.in` at install
  time with an absolute `Exec=` path, so launching from rofi works even when
  `~/.local/bin` is not on the launcher's `PATH`.
- `make check` runs `desktop-file-validate` against the generated entry.

## Troubleshooting

**Nothing pastes after Ctrl+C.**
On X11 and Wayland the clipboard is owned by the running application. If you close
InkClip before pasting, the image is gone. Keep InkClip open until you have pasted,
or use a clipboard manager (`clipman`, `copyq`, `parcellite`) that keeps history.

**Ctrl+C works in some apps but not others.**
A few apps only accept `text/uri-list` or a file drop rather than raw image data.
Use **Save PNG** and attach the file instead.

**Wayland: the paste target sees nothing at all.**
Make sure the Qt Wayland platform plugin is installed:

```bash
sudo pacman -S qt6-wayland
```

If a specific app still misbehaves, try forcing X11/XWayland for InkClip:

```bash
QT_QPA_PLATFORM=xcb python main.py
```

**InkClip does not show up in rofi.**
Check the entry landed and is valid:

```bash
ls ~/.local/share/applications/inkclip.desktop
desktop-file-validate ~/.local/share/applications/inkclip.desktop
```

If it is there but rofi still misses it, you have the desktop cache enabled
(`drun-use-desktop-cache: true` in `~/.config/rofi/config.rasi`) — either drop that
line or refresh with `rofi -show drun -drun-reload-desktop-cache`.

**The rofi entry has no icon.**
rofi hides icons unless you ask for it. Run `rofi -show drun -show-icons`, or add
`show-icons: true;` to the `configuration { ... }` block in
`~/.config/rofi/config.rasi`.

**`ModuleNotFoundError: No module named 'PySide6'`.**
Install it with `sudo pacman -S pyside6`, or activate your virtualenv and run
`pip install -r requirements.txt`.

**Stylus input does nothing.**
Qt needs tablet support from the platform plugin. On X11 make sure
`xf86-input-wacom` is installed; on Wayland the compositor handles it natively.
Mouse drawing always works regardless.
