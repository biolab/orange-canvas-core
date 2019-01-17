from typing import Callable, Any, Sequence, NamedTuple

from AnyQt.QtCore import Qt, QSortFilterProxyModel, QModelIndex


class FilterProxyModel(QSortFilterProxyModel):
    """
    A simple filter proxy model with settable filter predicates.

    Example
    -------
    >>> proxy = FilterProxyModel()
    >>> proxy.setFilters([
    ...     FilterProxyModel.Filter(0, Qt.DisplayRole, lambda value: value < 1)
    ... ])
    """
    Filter = NamedTuple("Filter", [
        ("column", int),
        ("role", Qt.ItemDataRole),
        ("predicate", Callable[[Any], bool])
    ])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__filters = []

    def setFilters(self, filters):
        # type: (Sequence[FilterProxyModel.Filter]) -> None
        filters = [FilterProxyModel.Filter(f.column, f.role, f.predicate)
                   for f in filters]
        self.__filters = filters
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        # type: (int, QModelIndex) -> bool
        source = self.sourceModel()

        def apply(f):
            index = source.index(row, f.column, parent)
            data = source.data(index, f.role)
            try:
                return f.predicate(data)
            except (TypeError, ValueError):
                return False

        return all(apply(f) for f in self.__filters)
