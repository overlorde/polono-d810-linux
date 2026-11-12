# Polono D810 – Linux driver

A small CUPS driver for the Polono D810 portable A4/Letter thermal printer.
Polono ships drivers for Windows and macOS only; this makes the printer usable
from Linux over USB.

Unofficial. Not affiliated with or endorsed by Polono. The protocol was worked
out for interoperability by studying how the vendor's macOS CUPS filter talks
to the printer; no vendor files are included here.

Write-up: <https://farhansaif.xyz/blog/polono-d810-linux-driver/>

## Status

- Confirmed: text printed legibly on thermal paper (a shop receipt) in roll mode,
  on Linux Mint 22.3 with firmware 1.0.5.
- Not yet checked: a full A4/Letter page on real thermal sheets (margins and
  page size may need adjusting), and the fold, label and tattoo media types.
- USB only. Bluetooth is not implemented.

## Files

| File | What it does |
|---|---|
| `d810.py` | Protocol + encoder. PDF → Ghostscript (203 dpi gray) → 1-bit → D810 bytes. Also a CLI. |
| `cups/d810-filter` | CUPS filter. Reads PPD defaults + job options, calls `d810.encode()`. |
| `ppd/polono-d810.ppd` | Paper sizes (A4/Letter/Legal), paper type, darkness. |
| `install.sh` / `uninstall.sh` | Copy files into CUPS and create/remove the queue. |

## Install

Needs CUPS, Ghostscript and Python 3 with Pillow (`python3-pil`).
Plug the printer in and turn it on first.

```bash
sudo ./install.sh
```

Then print from any app to **Polono D810**, or:

```bash
lp -d Polono_D810 file.pdf
lp -d Polono_D810 -o PageSize=Letter -o MediaType=Roll -o Darkness=Medium file.pdf
```

Remove with `sudo ./uninstall.sh`.

## Printer side

- Thermal paper only. A fingernail scratch should leave a dark mark; plain
  paper feeds through and stays blank.
- Printing side faces up.
- Size switch underneath: **210** = A4, **216** = Letter/Legal.
- Load paper until it is pulled in and the light is **green**.
  Red light = no paper; the printer silently drops jobs.

## Protocol

```
00 x128                 wake
10 FF F1 03             start job
1F 90 01 <mm>           paper width (D2 = 210, D8 = 216)
1F 80 01 <type>         10 roll, 30 fold, 20 label, 40 tattoo
10 FF 10 00 <0..2>      darkness low/medium/high
1F 11 51                fold and label paper only (meaning not decoded)
1D 76 30 00 wL wH hL hH data   raster, 1 = black, MSB first, whole page in one block
1D 0C                   fold/label: feed to the next mark
1B 4A <n>               roll (n = 80) / tattoo (n = F0): fixed feed in dots
10 FF FE 45             end job
```

Queries (replies are unframed: ASCII for strings, raw bytes for numbers):

| Query | Reply |
|---|---|
| `10 FF 40` | status: `00` ready, `04` no paper |
| `10 FF 50 F1` | battery level |
| `10 FF 20 F0` | model |
| `10 FF 20 F1` | firmware version |
| `10 FF 20 F2` | serial number |

The printer also sends a bare `OK` after a finished job.

## Debug

```bash
# encode without printing
python3 d810.py test.pdf -o out.bin

# see what the filter did for a real job
sudo cupsctl --debug-logging
lp -d Polono_D810 test.pdf
sudo grep d810 /var/log/cups/error_log | tail
sudo cupsctl --no-debug-logging
```

## License

MIT, see `LICENSE`.
