"""
Node/Link layout.

"""
from operator import attrgetter

import sip

from AnyQt.QtWidgets import QGraphicsObject, QApplication
from AnyQt.QtCore import QRectF, QLineF, QEvent

from .items import LinkItem, SourceAnchorItem, SinkAnchorItem
from .items.utils import (
    invert_permutation_indices, argsort, composition, linspace_trunc
)


class AnchorLayout(QGraphicsObject):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.setFlag(QGraphicsObject.ItemHasNoContents)

        self.__layoutPending = False
        self.__isActive = False
        self.__invalidatedAnchors = []
        self.__enabled = True

    def boundingRect(self):
        return QRectF()

    def activate(self):
        if self.isEnabled() and not self.__isActive:
            self.__isActive = True
            try:
                self._doLayout()
            finally:
                self.__isActive = False
                self.__layoutPending = False

    def isActivated(self):
        return self.__isActive

    def _doLayout(self):
        if not self.isEnabled():
            return

        scene = self.scene()
        items = scene.items()
        links = [item for item in items if isinstance(item, LinkItem)]
        point_pairs = [(link.sourceAnchor, link.sinkAnchor) for link in links]
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
        self.invalidateAnchorItem(link.sourceItem.outputAnchorItem)
        self.invalidateAnchorItem(link.sinkItem.inputAnchorItem)

        self.scheduleDelayedActivate()

    def invalidateNode(self, node):
        self.invalidateAnchorItem(node.inputAnchorItem)
        self.invalidateAnchorItem(node.outputAnchorItem)

        self.scheduleDelayedActivate()

    def invalidateAnchorItem(self, anchor):
        self.__invalidatedAnchors.append(anchor)

        scene = self.scene()
        if isinstance(anchor, SourceAnchorItem):
            links = scene.node_output_links(anchor.parentNodeItem())
            getter = composition(attrgetter("sinkItem"),
                                 attrgetter("inputAnchorItem"))
        elif isinstance(anchor, SinkAnchorItem):
            links = scene.node_input_links(anchor.parentNodeItem())
            getter = composition(attrgetter("sourceItem"),
                                 attrgetter("outputAnchorItem"))
        else:
            raise TypeError(type(anchor))

        self.__invalidatedAnchors.extend(map(getter, links))

        self.scheduleDelayedActivate()

    def scheduleDelayedActivate(self):
        if self.isEnabled() and not self.__layoutPending:
            self.__layoutPending = True
            QApplication.postEvent(self, QEvent(QEvent.LayoutRequest))

    def __delayedActivate(self):
        if self.__layoutPending:
            self.activate()

    def event(self, event):
        if event.type() == QEvent.LayoutRequest:
            self.activate()
            return True

        return super().event(event)


def angle(point1, point2):
    """Return the angle between the two points in range from -180 to 180.
    """
    angle = QLineF(point1, point2).angle()
    if angle > 180:
        return angle - 360
    else:
        return angle
