import sys
from itertools import islice, count
from operator import itemgetter

import typing
from typing import List, Iterable, Optional, Callable, Any, Union, Tuple

from AnyQt.QtCore import QPointF, QLineF
from AnyQt.QtGui import (
    QColor, QRadialGradient, QPainterPathStroker, QPainterPath, QPen
)

from AnyQt.QtWidgets import QGraphicsItem

if typing.TYPE_CHECKING:
    T = typing.TypeVar("T")
    A = typing.TypeVar("A")
    B = typing.TypeVar("B")
    C = typing.TypeVar("C")


def composition(f, g):
    # type: (Callable[[A], B], Callable[[B], C]) -> Callable[[A], C]
    """
    Return a composition of two functions.
    """
    def fg(arg):  # type: (A) -> C
        return g(f(arg))
    return fg


def argsort(iterable, key=None, reverse=False):
    # type: (Iterable[T], Optional[Callable[[T], Any]], bool) -> List[int]
    """
    Return indices that sort elements of iterable in ascending order.

    A custom key function can be supplied to customize the sort order, and the
    reverse flag can be set to request the result in descending order.

    Parameters
    ----------
    iterable : Iterable[T]
    key : Callable[[T], Any]
    reverse : bool

    Returns
    -------
    indices : List[int]
    """
    if key is None:
        key_ = itemgetter(0)
    else:
        key_ = composition(itemgetter(0), key)
    ordered = sorted(zip(iterable, count(0)), key=key_, reverse=reverse)
    return list(map(itemgetter(1), ordered))


def linspace(count):
    # type: (int) -> Iterable[float]
    """
    Return `count` evenly spaced points from 0..1 interval.

    >>> list(linspace(3)))
    [0.0, 0.5, 1.0]
    """
    if count > 1:
        return (i / (count - 1) for i in range(count))
    elif count == 1:
        return (_ for _ in (0.0,))
    elif count == 0:
        return (_ for _ in ())
    else:
        raise ValueError("Count must be non-negative")


def linspace_trunc(count):
    # type: (int) -> Iterable[float]
    """
    Return `count` evenly spaced points from 0..1 interval *excluding*
    both end points.

    >>> list(linspace_trunc(3))
    [0.25, 0.5, 0.75]
    """
    return islice(linspace(count + 2), 1, count + 1)


def sample_path(path, num=10):
    # type: (QPainterPath, int) -> List[QPointF]
    """
    Sample `num` equidistant points from the `path` (`QPainterPath`).
    """
    return [path.pointAtPercent(p) for p in linspace(num)]


def saturated(color, factor=150):
    # type: (QColor, int) -> QColor
    """Return a saturated color.
    """
    h = color.hsvHueF()
    s = color.hsvSaturationF()
    v = color.valueF()
    a = color.alphaF()
    s = factor * s / 100.0
    s = max(min(1.0, s), 0.0)
    return QColor.fromHsvF(h, s, v, a).convertTo(color.spec())


def radial_gradient(color, color_light=50):
    # type: (QColor, Union[int, QColor]) -> QRadialGradient
    """
    radial_gradient(QColor, QColor)
    radial_gradient(QColor, int)

    Return a radial gradient. `color_light` can be a QColor or an int.
    In the later case the light color is derived from `color` using
    `saturated(color, color_light)`.

    """
    if not isinstance(color_light, QColor):
        color_light = saturated(color, color_light)
    gradient = QRadialGradient(0.5, 0.5, 0.5)
    gradient.setColorAt(0.0, color_light)
    gradient.setColorAt(0.5, color_light)
    gradient.setColorAt(1.0, color)
    gradient.setCoordinateMode(QRadialGradient.ObjectBoundingMode)
    return gradient


def toGraphicsObjectIfPossible(item):
    """Return the item as a QGraphicsObject if possible.

    This function is intended as a workaround for a problem with older
    versions of PyQt (< 4.9), where methods returning 'QGraphicsItem *'
    lose the type of the QGraphicsObject subclasses and instead return
    generic QGraphicsItem wrappers.
    """
    if item is None:
        return None

    obj = item.toGraphicsObject()
    return item if obj is None else obj


def uniform_linear_layout_trunc(points):
    # type: (List[float]) -> List[float]
    """
    Layout the points (a list of floats in 0..1 range) in a uniform
    linear space (truncated) while preserving the existing sorting order.
    """
    indices = argsort(points)
    indices = invert_permutation_indices(indices)
    space = list(linspace_trunc(len(indices)))
    return [space[i] for i in indices]


def invert_permutation_indices(indices):
    # type: (List[int]) -> List[int]
    """
    Invert the permutation given by indices.
    """
    inverted = [sys.maxsize] * len(indices)
    for i, index in enumerate(indices):
        inverted[index] = i
    return inverted


def stroke_path(path, pen):
    # type: (QPainterPath, QPen) -> QPainterPath
    """Create a QPainterPath stroke from the `path` drawn with `pen`.
    """
    stroker = QPainterPathStroker()
    stroker.setCapStyle(pen.capStyle())
    stroker.setJoinStyle(pen.joinStyle())
    stroker.setMiterLimit(pen.miterLimit())
    stroker.setWidth(max(pen.widthF(), 1e-9))

    return stroker.createStroke(path)


def bezier_subdivide(cp, t):
    # type: (List[QPointF], float) -> Tuple[List[QPointF], List[QPointF]]
    """
    Subdivide a cubic bezier curve defined by the control points `cp`.

    Parameters
    ----------
    cp : List[QPointF]
        The control points for a cubic bezier curve.
    t : float
        The cut point; a value between 0 and 1.

    Returns
    -------
    cp : Tuple[List[QPointF], List[QPointF]]
        Two lists of new control points for the new left and right part
        respectively.
    """
    # http://www.cs.mtu.edu/~shene/COURSES/cs3621/NOTES/spline/Bezier/bezier-sub.html
    c00, c01, c02, c03 = cp

    c10 = c00 * (1 - t) + c01 * t
    c11 = c01 * (1 - t) + c02 * t
    c12 = c02 * (1 - t) + c03 * t

    c20 = c10 * (1 - t) + c11 * t
    c21 = c11 * (1 - t) + c12 * t

    c30 = c20 * (1 - t) + c21 * t

    first = [c00, c10, c20, c30]
    second = [c30, c21, c12, c03]
    return first, second


def qpainterpath_simple_split(path, t):
    # type: (QPainterPath, float) -> Tuple[QPainterPath, QPainterPath]
    """
    Split a QPainterPath defined simple curve.

    The path must be either empty or composed of a single LineToElement or
    CurveToElement.

    Parameters
    ----------
    path : QPainterPath

    t : float
        Point where to split specified as a percentage along the path

    Returns
    -------
    splitpath: Tuple[QPainterPath, QPainterPath]
        A pair of QPainterPaths
    """
    assert path.elementCount() > 0
    el0 = path.elementAt(0)
    assert el0.type == QPainterPath.MoveToElement
    if path.elementCount() == 1:
        p1 = QPainterPath()
        p1.moveTo(el0.x, el0.y)
        return p1, QPainterPath(p1)

    el1 = path.elementAt(1)
    if el1.type == QPainterPath.LineToElement:
        pointat = path.pointAtPercent(t)
        l1 = QLineF(el0.x, el0.y, pointat.x(), pointat.y())
        l2 = QLineF(pointat.x(), pointat.y(), el1.x, el1.y)
        p1 = QPainterPath()
        p2 = QPainterPath()
        p1.moveTo(l1.p1())
        p1.lineTo(l1.p2())
        p2.moveTo(l2.p1())
        p2.lineTo(l2.p2())
        return p1, p2
    elif el1.type == QPainterPath.CurveToElement:
        c0, c1, c2, c3 = el0, el1, path.elementAt(2), path.elementAt(3)
        assert all(el.type == QPainterPath.CurveToDataElement
                   for el in [c2, c3])
        cp = [QPointF(el.x, el.y) for el in [c0, c1, c2, c3]]
        first, second = bezier_subdivide(cp, t)
        p1, p2 = QPainterPath(), QPainterPath()
        p1.moveTo(first[0])
        p1.cubicTo(*first[1:])
        p2.moveTo(second[0])
        p2.cubicTo(*second[1:])
        return p1, p2
    else:
        assert False
