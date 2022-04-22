from typing import Sequence

import numpy as np

from AnyQt.QtGui import QImage, QColor


def qrgb(
        r: Sequence[int], g: Sequence[int], b: Sequence[int]
) -> Sequence[int]:
    """A vectorized `qRgb`."""
    r, g, b = map(lambda a: np.asarray(a, dtype=np.uint32), (r, g, b))
    return (0xff << 24) | ((r & 0xff) << 16) | ((g & 0xff) << 8) | (b & 0xff)


def qrgba(
        r: Sequence[int], g: Sequence[int], b: Sequence[int], a: Sequence[int]
) -> Sequence[int]:
    """A vectorized `qRgba`."""
    r, g, b, a = map(lambda a: np.asarray(a, dtype=np.uint32), (r, g, b, a))
    return ((a & 0xff) << 24) | ((r & 0xff) << 16) | ((g & 0xff) << 8) | (b & 0xff)


def qgray(
        r: Sequence[int], g: Sequence[int], b: Sequence[int]
) -> Sequence[int]:
    """A vectorized `qGray`."""
    r, g, b = map(lambda a: np.asarray(a, dtype=np.uint16), (r, g, b))
    return (r * 11 + g * 16 + b * 5) // 32


def qred(rgb: Sequence[int]) -> Sequence[int]:
    """A vectorized `qRed`."""
    rgb = np.asarray(rgb, np.uint32)
    return (rgb >> 16) & 0xff


def qgreen(rgb: Sequence[int]) -> Sequence[int]:
    """A vectorized `qGreen`."""
    rgb = np.asarray(rgb, np.uint32)
    return (rgb >> 8) & 0xff


def qblue(rgb: Sequence[int]) -> Sequence[int]:
    """A vectorized `qBlue`."""
    rgb = np.asarray(rgb, np.uint32)
    return rgb & 0xff


def qalpha(rgb: Sequence[int]) -> Sequence[int]:
    """A vectorized `qAlpha`."""
    rgb = np.asarray(rgb, np.uint32)
    return (rgb >> 24) & 0xff


def grayscale_invert(
        src: QImage, foreground: QColor, background: QColor
) -> QImage:
    """
    Convert the `src` image to grayscale and invert it into background
    to foreground (gray) range.

    Parameters
    ----------
    src: QImage
    foreground: QColor
    background: QColor

    Returns
    -------
    image: QImage
    """
    image = src.convertToFormat(QImage.Format_ARGB32)
    size = image.size()
    w, h = shape = size.width(), size.height()
    buffer = image.bits().asarray(w * h * 4)
    view = np.frombuffer(buffer, np.uint32).reshape(shape)
    r, g, b, a = qred(view), qgreen(view), qblue(view), qalpha(view)
    gray = qgray(r, g, b)
    factor = gray / 255
    foreground = qgray(foreground.red(), foreground.blue(), foreground.green())
    background = qgray(background.red(), background.blue(), background.green())
    if foreground > background:
        minv_, maxv_ = background, foreground
    else:
        minv_, maxv_ = foreground, background
    inv = (1 - factor) * (maxv_ - minv_) + minv_
    inv = np.asarray(inv, np.uint8)
    rgba = qrgba(inv, inv, inv, a)
    res = QImage(w, h, QImage.Format_ARGB32)
    return qimage_copy_from_buffer(res, rgba)


def qimage_copy_from_buffer(image: QImage, data: np.ndarray) -> QImage:
    """
    Copy the `data` to `image`.

    Parameters
    ----------
    image: QImage
        The destination image.
    data: np.ndarray
        The raw source data in the same format as the `image`.
    """
    w, h = image.width(), image.height()
    if data.shape != (w, h):
        raise ValueError(
            f"Wrong data.shape (expected ({w}, {h}) got {data.shape})"
        )
    d = image.depth() // 8
    dtype = {
        1: np.uint8, 2: np.uint16, 4: np.uint32, 8: np.uint64
    }[d]
    dest = image.bits().asarray(w * h * d)
    dest = np.frombuffer(dest, dtype).reshape((w, h))
    dest[:] = data
    return image
