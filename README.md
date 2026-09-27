# Auto Clicker

A desktop tool with two modes:
- **Image match** — clicks wherever a target image appears on screen,
  optionally restricted to a region you draw with your mouse.
- **Fixed point** — click a spot on screen once to set it, then click that
  exact spot repeatedly at a clicks-per-second rate you choose. No image
  required — this is a classic auto-clicker.

## How it works

**Image match mode:**
1. **Load a target image** — a screenshot/crop of the button, icon, or element
   you want clicked (PNG/JPG). Crop it tight for accurate matching.
2. **(Optional) Select a region** — drag a box on screen. The app will only
   search inside that box, so it won't click matches elsewhere.
3. **Set confidence & check interval** — how strict the match needs to be
   (0.85 is a good default) and how often to check (in seconds). The check
   interval is effectively the click rate in this mode, since it has to look
   before it can click.
4. **Start** — the app screenshots the region on a loop, looks for your image,
   and clicks the center of the best match once it clears your confidence
   threshold.

**Fixed point mode:**
1. **Set Click Point** — click the exact spot on screen you want targeted.
2. **Set clicks per second** — how fast to click that spot. No image lookup
   overhead, so this can go much faster than image match mode.
3. **Start.**

**Hotkeys:** Start defaults to F1, Stop to F2, and both work even when the
app window isn't focused — handy for games/apps that need to stay in focus.
Click "Change" next to either to press any key/combo you want instead.

Move your mouse to any screen corner at any time to immediately abort
(PyAutoGUI's built-in fail-safe).

## Setup

```bash
pip install -r requirements.txt
python auto_clicker.py
```

### Platform notes
- **Windows**: works out of the box. If hotkeys don't respond, try running as
  Administrator.
- **macOS**: go to *System Settings → Privacy & Security → Accessibility* and
  *Screen Recording*, and enable your terminal app (or Python) in both — macOS
  blocks simulated clicks, screenshots, and global hotkeys otherwise.
- **Linux**: install a screenshot backend first: `sudo apt install scrot`
  (X11) or use `gnome-screenshot` on GNOME/Wayland setups. Global hotkeys
  need to run as root on some distros because of how the `keyboard` library
  hooks input.

### A note about hotkeys and antivirus
The `keyboard` library works by installing a low-level keyboard hook so it
can catch F1/F2 (or whatever you set) even when the app isn't focused. That's
the same general mechanism keyloggers use, just aimed at one specific key —
this app doesn't log or store anything you type. Still, some antivirus tools
flag PyInstaller-built exes that use this kind of hook as suspicious by
default. If that happens, it's a false positive; you may need to allow the
file through your antivirus.

## Tips
- Crop the target image as tightly as possible around a distinctive, unique
  part of what you're clicking — less background makes matching more reliable.
- If it's clicking the wrong thing, raise the confidence value (e.g. 0.9–0.95)
  or narrow the search region.
- If it's not clicking at all, lower the confidence slightly, or re-crop the
  target image (screen scaling/DPI can shift exact pixels).
- Use "Stop after N clicks" if you only want it to fire a fixed number of
  times.

## Packaging as a standalone app (no Python required to run it)

If you want to share this with someone who doesn't have Python installed,
package it into a single executable with PyInstaller. Run the build **on
the same OS you want the app to run on** (a Windows build must be made on
Windows, a Mac build on a Mac — PyInstaller can't cross-compile).

**Windows:**
```
build_windows.bat
```
Produces `dist\AutoClicker.exe` — a single file you can send to anyone.
They just double-click it.

**Mac / Linux:**
```
chmod +x build_mac_linux.sh
./build_mac_linux.sh
```
Produces `dist/AutoClicker.app` (Mac) or `dist/AutoClicker` (Linux).

Notes:
- The resulting file is larger (~80-150MB) because it bundles the Python
  interpreter and libraries (opencv especially) — that's normal.
- **Windows Defender/SmartScreen and macOS Gatekeeper** may flag a freshly
  built, unsigned exe as "unrecognized" the first time someone runs it,
  since it isn't from a verified publisher. That's expected for any indie
  auto-clicker app — the user typically clicks "More info → Run anyway"
  (Windows) or right-clicks → Open (Mac) once. Code-signing certificates
  exist to avoid this but cost money and aren't necessary just to share
  the tool with friends/family.
- Rebuild and re-share the exe any time you change auto_clicker.py.

## A note on use
This is a general-purpose automation tool. If you're using it against a game
or app, check that automating clicks doesn't violate that service's terms —
many games and platforms prohibit bots/auto-clickers even for legitimate
grinding.
