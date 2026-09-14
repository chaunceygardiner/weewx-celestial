#!/usr/bin/env python3
"""The contrast of a text color on its ground, by both measures.

Run it on EVERY change to a text color or to the ground under text, at the
moment the change is made -- not after the page has shipped and the reader
has found it.  It takes a second:

    tools/contrast.py '#ffffff' '#ff0000'
    tools/contrast.py '#1a0000' 'rgba(255,255,255,.55)' '#ff0000'

The second form is a translucent ground laid over what is beneath it (a
chip tinted over a colored header); give as many layers as there are,
innermost first.  The text color may be translucent too.

WHY TWO MEASURES.  The WCAG 2 ratio is the one the standard names, and it
is wrong in a known direction: it overrates dark text on saturated,
mid-luminance colors.  Dark ink on the plate's pure red scores 5.03 --
comfortably over AA -- and on an iPhone the magnitude in the Seismograph's
marker could not be read (John, 2026-09-13).  APCA, the model written to
replace it, scores the same pair Lc 39.5; white on that red, which the
ratio fails at 4.00, scores Lc 69.6 and reads plainly.  Neither number is
enough alone, so both are printed, each against its own bars.

APCA here is APCA-W3 0.0.98G-4g (the constants below), the version the
W3C Silver drafts cite.  Lc is signed: positive is dark text on a lighter
ground, negative is light text on a darker one; the bars compare its size.

tests/test_celestial.py imports wcag() and apca() from this file, so the
suite and the command line cannot disagree about a number.
"""
import re
import sys

# APCA-W3 0.0.98G-4g
_TRC = 2.4
_COEF = (0.2126729, 0.7151522, 0.0721750)
_NORM_BG, _NORM_TXT, _REV_TXT, _REV_BG = 0.56, 0.57, 0.62, 0.65
_BLK_THRS, _BLK_CLMP = 0.022, 1.414
_SCALE = 1.14
_OFFSET = 0.027
_DELTA_Y_MIN = 0.0005
_LO_CLIP = 0.1

# The bars each measure is read against.  WCAG 2: AA for small text, and
# for large (24px, or 18.66px bold).  APCA Bronze: body text, other content
# text, large or heavy text, and non-text marks.
WCAG_BARS = (('AA small text', 4.5), ('AA large text', 3.0))
APCA_BARS = (('body text', 75), ('content text', 60), ('large text', 45), ('non-text', 30))


def parse(color):
    """'#rgb', '#rrggbb', 'rgb(r,g,b)' or 'rgba(r,g,b,a)' -> (r, g, b, a)."""
    c = color.strip().lower()
    m = re.fullmatch(r'#([0-9a-f]{3}|[0-9a-f]{6})', c)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = ''.join(ch * 2 for ch in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)
    m = re.fullmatch(r'rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)', c)
    if m:
        a = 1.0 if m.group(4) is None else float(m.group(4))
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)), a)
    raise ValueError('not a color this reads: %r' % color)


def flatten(*layers):
    """Colors from the top down to an opaque bottom -> the opaque (r, g, b)
    a reader sees.  `flatten(chip, header)` is the chip over the header."""
    colors = [parse(c) if isinstance(c, str) else c for c in layers]
    r, g, b, a = colors[-1]
    if a < 1:
        raise ValueError('the bottom layer must be opaque: %r' % (layers[-1],))
    for top in reversed(colors[:-1]):
        tr, tg, tb, ta = top
        r, g, b = (tr * ta + r * (1 - ta), tg * ta + g * (1 - ta), tb * ta + b * (1 - ta))
    return (r, g, b)


def _wcag_lum(rgb):
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def wcag(text, ground):
    """The WCAG 2 contrast ratio of two opaque (r, g, b) colors."""
    hi, lo = sorted((_wcag_lum(text), _wcag_lum(ground)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _apca_y(rgb):
    y = sum(k * (v / 255.0) ** _TRC for k, v in zip(_COEF, rgb))
    return y + (_BLK_THRS - y) ** _BLK_CLMP if y <= _BLK_THRS else y


def apca(text, ground):
    """APCA Lc of opaque (r, g, b) text on an opaque (r, g, b) ground."""
    ty, gy = _apca_y(text), _apca_y(ground)
    if abs(gy - ty) < _DELTA_Y_MIN:
        return 0.0
    if gy > ty:
        s = (gy ** _NORM_BG - ty ** _NORM_TXT) * _SCALE
        return 0.0 if s < _LO_CLIP else (s - _OFFSET) * 100
    s = (gy ** _REV_BG - ty ** _REV_TXT) * _SCALE
    return 0.0 if s > -_LO_CLIP else (s + _OFFSET) * 100


def measure(text, *ground):
    """Text over a ground given as layers (see flatten) -> (wcag, apca)."""
    under = flatten(*ground)
    over = flatten(text, under + (1.0,))
    return wcag(over, under), apca(over, under)


def main(argv):
    if len(argv) < 3:
        sys.stderr.write(__doc__.split('\n\n')[1] + '\n')
        return 2
    ratio, lc = measure(argv[1], *argv[2:])
    print('WCAG 2  %5.2f   %s' % (ratio, ', '.join(
        '%s %s: %s' % (name, bar, 'pass' if ratio >= bar else 'FAIL') for name, bar in WCAG_BARS)))
    print('APCA  Lc %5.1f   %s' % (lc, ', '.join(
        '%s %d: %s' % (name, bar, 'pass' if abs(lc) >= bar else 'FAIL') for name, bar in APCA_BARS)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
