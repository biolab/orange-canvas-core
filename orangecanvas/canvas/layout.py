"""
Node/Link layout.

"""
from operator import attrgetter

import typing
from typing import Optional, Any, List

import sip

from AnyQt.QtWidgets import QGraphicsObject, QApplication, QGraphicsItem
from AnyQt.QtCore import QRectF, QLineF, QEvent, QPointF

from .items import (
    NodeItem, LinkItem, NodeAnchorItem, SourceAnchorItem, SinkAnchorItem
)
from .items.utils import (
    invert_permutation_indices, argsort, composition, linspace_trunc
)

if typing.TYPE_CHECKING:
    from .scene import CanvasScene


class AnchorLayout(QGraphicsObject):
    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QGraphicsItem], Any) -> None
        super().__init__(parent, **kwargs)
        self.setFlag(QGraphicsObject.ItemHasNoContents)

        self.__layoutPending = False
        self.__isActive = False
        self.__invalidatedAnchors = []  # type: List[NodeAnchorItem]
        self.__enabled = True

    def boundingRect(self):  # type: () -> QRectF
        return QRectF()

    def activate(self):  # type: () -> None
        """
        Immediately layout all anchors.
        """
        if self.isEnabled() and not self.__isActive:
            self.__isActive = True
            try:
                self._doLayout()
            finally:
                self.__isActive = False
                self.__layoutPending = False

    def isActivated(self):  # type: () -> bool
        """
        Is the layout currently activated (in :func:`activate()`)
        """
        return self.__isActive

    def _doLayout(self):  # type: () -> None
        if not self.isEnabled():
            return

        scene = self.scene()
        items = scene.items()
        links = [item for item in items if isinstance(item, LinkItem)]
        point_pairs = [(link.sourceAnchor, link.sinkAnchor)
                       for link in links
                       if link.sourceAnchor is not None
                          and link.sinkAnchor is not None]
        point_pairs += [(a, b) for b, a in point_pairs]
        to_other = dict(point_pairs)

        anchors = set(self.__invalidatedAnchors)

        for anchor_item in anchors:
            if sip.isdeleted(anchor_item):
                continue

            points = anchor_item.anchorPoints()
            anchor_pos = anchor_item.mapToScene(anchor_item.pos())
            others = [to_other[point] for point in points]

            if isinstance(anchor_item, SourceAnchorItem):
                others_angle = [-angle(anchor_pos, other.anchorScenePos())
                                for other in others]
            else:
                others_angle = [angle(other.anchorScenePos(), anchor_pos)
                                for other in others]

            indices = argsort(others_angle)
            # Invert the indices.
            indices = invert_permutation_indices(indices)

            positions = list(linspace_trunc(len(points)))
            positions = [positions[i] for i in indices]
            anchor_item.setAnchorPositions(positions)

        self.__invalidatedAnchors = []

    def invalidateLink(self, link):
        # type: (LinkItem) -> None
        """
        Invalidate the anchors on `link` and schedule an update.

        Parameters
        ----------
        link : LinkItem
        """
        if link.sourceItem is not None:
            self.invalidateAnchorItem(link.sourceItem.outputAnchorItem)
        if link.sinkItem is not None:
            self.invalidateAnchorItem(link.sinkItem.inputAnchorItem)

    def invalidateNode(self, node):
        # type: (NodeItem) -> None
        """
        Invalidate the anchors on `node` and schedule an update.

        Parameters
        ----------
        node : NodeItem
        """
        self.invalidateAnchorItem(node.inputAnchorItem)
        self.invalidateAnchorItem(node.outputAnchorItem)

        self.scheduleDelayedActivate()

    def invalidateAnchorItem(self, anchor):
        # type: (NodeAnchorItem) -> None
        """
        Invalidate the all links on `anchor`.

        Parameters
        ----------
        anchor : NodeAnchorItem
        """
        self.__invalidatedAnchors.append(anchor)

        scene = self.scene()  # type: CanvasScene
        node = anchor.parentNodeItem()
        if node is None:
            return
        if isinstance(anchor, SourceAnchorItem):
            links = scene.node_output_links(node)
            getter = composition(attrgetter("sinkItem"),
                                 attrgetter("inputAnchorItem"))
        elif isinstance(anchor, SinkAnchorItem):
            links = scene.node_input_links(node)
            getter = composition(attrgetter("sourceItem"),
                                 attrgetter("outputAnchorItem"))
        else:
            raise TypeError(type(anchor))

        self.__invalidatedAnchors.extend(map(getter, links))

        self.scheduleDelayedActivate()

    def scheduleDelayedActivate(self):
        # type: () -> None
        """
        Schedule an layout pass
        """
        if self.isEnabled() and not self.__layoutPending:
            self.__layoutPending = True
            QApplication.postEvent(self, QEvent(QEvent.LayoutRequest))

    def __delayedActivate(self):
        # type: () -> None
        if self.__layoutPending:
            self.activate()

    def event(self, event):
        # type: (QEvent)->bool
        if event.type() == QEvent.LayoutRequest:
            self.activate()
            return True
        return super().event(event)


def angle(point1, point2):
    # type: (QPointF, QPointF) -> float
    """
    Return the angle between the two points in range from -180 to 180.
    """
    angle = QLineF(point1, point2).angle()
    if angle > 180:
        return angle - 360
    else:
        return angle
