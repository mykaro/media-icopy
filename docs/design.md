# Media iCopy Design Rules (Fallout Aesthetic)

The `Media iCopy` interface follows a **Fallout / RobCo terminal** style: retro console, strict geometric forms, monospace font, dark CRT background, and neon-green accents.

## Core Style
- No rounded corners: always `corner_radius=0`
- Monospace font only: `Consolas`
- All interface text in uppercase
- Console-style prefixes used for labels and logs
- Modern UI effects are forbidden: shadows, gradients, rounded corners

## Colours (`src/gui/constants.py`)
- `T_GREEN` `#00ff41` — active elements, accents, progress
- `T_DIM` `#008f11` — regular text, labels, inactive elements
- `T_DARK` `#003b00` — borders and hover effects
- `T_BG` `#080808` — primary background
- `T_PANEL` `#101010` — background for panels and lists
- `T_RED` `#ff3333` — stop button and critical errors

## Interface Rules
- Labels use the prefix: `> `
- Buttons:
  - transparent background (Exception: Notification indicators may use inverted colors, e.g., `T_GREEN` background with `T_BG` text to draw attention)
  - no border
  - text formatted as `[ ACTION ]`
  - width aligned with spaces
- Folders displayed as: `DIR >> {name}`

## Animations
- A `>` symbol pulses next to the "SUPPORT THE PROJECT" button every 500 ms (`T_GREEN` ↔ `T_BG`)
- The "SUPPORT THE PROJECT" button highlights 3 seconds after launch (1 s on / 4 s off cycle)
- `"Developed by Mykaro"` types out like a typewriter (with a `_` cursor) and repeats every 10 seconds
- Log format:
  - info: `> `
  - error: `> [! ERR !] `
  - warning: `> [? WRN ?] `
  - time: `HHMM:SS`

## Mandatory
All new interface elements must use this colour palette, square geometry, and preserve the Fallout terminal style.
