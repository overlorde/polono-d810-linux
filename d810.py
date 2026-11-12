#!/usr/bin/python3
"""
Polono D810 encoder for Linux.

Turns a PDF into the byte stream the D810 expects. The command layout was
recovered from Polono's own macOS CUPS filter (rastertolabel, model 20):

    00 x128                 wake / sync
    10 FF F1 03             start job
    1F 90 01 <mm>           paper width in mm (0xD2 = A4, 0xD8 = Letter)
    1F 80 01 <media>        media type (fold / roll / label / tattoo)
    10 FF 10 00 <0..2>      darkness
    1F 11 51                fold and label paper only
    1D 76 30 00 w w h h ... ESC/POS raster image, 1 = black, MSB first
    1D 0C / 1B 4A n         page end: next mark (fold, label) or fixed feed (roll, tattoo)
    10 FF FE 45             end job

Usage:
    d810.py input.pdf > out.bin
    d810.py input.pdf --paper letter --darkness high -o out.bin
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Iterator

from PIL import Image

DPI = 203


class Paper(Enum):
    # (width in mm sent to the printer, printable width/height in points from the PPD)
    A4 = (0xD2, 572, 826)
    LETTER = (0xD8, 589, 790)
    LEGAL = (0xD8, 589, 993)

    @property
    def width_mm(self) -> int:
        return self.value[0]

    @property
    def size_px(self) -> tuple[int, int]:
        # Width is rounded up to a whole byte so each raster row lines up.
        w_pt, h_pt = self.value[1], self.value[2]
        w = round(w_pt / 72 * DPI)
        h = round(h_pt / 72 * DPI)
        return (w + 7) // 8 * 8, h


class Media(Enum):
    FOLD = 0x30
    ROLL = 0x10
    LABEL = 0x20
    TATTOO = 0x40


class Darkness(Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2


@dataclass
class JobSettings:
    paper: Paper = Paper.A4
    media: Media = Media.FOLD
    darkness: Darkness = Darkness.HIGH


class D810Protocol:
    """Builds the raw command bytes. Knows nothing about PDFs or files."""

    def __init__(self, settings: JobSettings) -> None:
        self.s = settings

    def job_header(self) -> bytes:
        out = bytearray(b"\x00" * 128)
        out += b"\x10\xff\xf1\x03"
        out += bytes([0x1F, 0x90, 0x01, self.s.paper.width_mm])
        out += bytes([0x1F, 0x80, 0x01, self.s.media.value])
        out += bytes([0x10, 0xFF, 0x10, 0x00, self.s.darkness.value])
        # Polono's driver sends this for the two media types that have gaps/marks.
        if self.s.media in (Media.FOLD, Media.LABEL):
            out += b"\x1f\x11\x51"
        return bytes(out)

    @staticmethod
    def raster(img: Image.Image) -> bytes:
        """GS v 0 block for a 1-bit image (PIL uses 1 = white, printer wants 1 = black)."""
        bw = img.convert("1")
        width_bytes = (bw.width + 7) // 8
        data = bytes(b ^ 0xFF for b in bw.tobytes())
        head = b"\x1d\x76\x30\x00" + width_bytes.to_bytes(2, "little") + bw.height.to_bytes(2, "little")
        return head + data

    def page_end(self) -> bytes:
        # Fold and label paper: let the printer find the next mark/gap itself.
        if self.s.media in (Media.FOLD, Media.LABEL):
            return b"\x1d\x0c"
        # Continuous media: fixed feed (ESC J n, in dots), same lengths as Polono's driver.
        feed_dots = 0xF0 if self.s.media is Media.TATTOO else 0x80
        return b"\x1b\x4a" + bytes([feed_dots])

    @staticmethod
    def job_footer() -> bytes:
        return b"\x10\xff\xfe\x45"


class PdfRasterizer:
    """Renders PDF pages to grayscale images at printer resolution using Ghostscript."""

    def __init__(self, paper: Paper) -> None:
        self.w, self.h = paper.size_px

    def pages(self, pdf: Path) -> Iterator[Image.Image]:
        with tempfile.TemporaryDirectory() as tmp:
            pattern = Path(tmp) / "p%04d.png"
            subprocess.run(
                [
                    "gs", "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE",
                    "-sDEVICE=pnggray", f"-r{DPI}",
                    f"-g{self.w}x{self.h}", "-dFIXEDMEDIA", "-dPDFFitPage",
                    f"-sOutputFile={pattern}", str(pdf),
                ],
                check=True,
                # stdout carries printer data in the CUPS filter, keep gs chatter off it
                stdout=sys.stderr,
            )
            for png in sorted(Path(tmp).glob("p*.png")):
                with Image.open(png) as im:
                    # Floyd-Steinberg dithering happens in convert("1").
                    yield im.convert("L").copy()


def encode(pdf: Path, settings: JobSettings, out: BinaryIO) -> int:
    proto = D810Protocol(settings)
    out.write(proto.job_header())
    count = 0
    for page in PdfRasterizer(settings.paper).pages(pdf):
        out.write(proto.raster(page))
        out.write(proto.page_end())
        count += 1
    out.write(proto.job_footer())
    out.flush()
    return count


def main() -> None:
    ap = argparse.ArgumentParser(description="Encode a PDF for the Polono D810")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    ap.add_argument("--paper", choices=[p.name.lower() for p in Paper], default="a4")
    ap.add_argument("--media", choices=[m.name.lower() for m in Media], default="fold")
    ap.add_argument("--darkness", choices=[d.name.lower() for d in Darkness], default="high")
    args = ap.parse_args()

    settings = JobSettings(
        paper=Paper[args.paper.upper()],
        media=Media[args.media.upper()],
        darkness=Darkness[args.darkness.upper()],
    )

    if args.output:
        with open(args.output, "wb") as f:
            n = encode(args.pdf, settings, f)
    else:
        n = encode(args.pdf, settings, sys.stdout.buffer)
    print(f"encoded {n} page(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
