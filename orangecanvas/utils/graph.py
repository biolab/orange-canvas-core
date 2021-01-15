import itertools
from collections import deque
from typing import TypeVar, Iterable, Callable, Set, List, Hashable

__all__ = [
    "traverse_bf", "strongly_connected_components"
]

H = TypeVar("H", bound=Hashable)


def traverse_bf(start, expand):
    # type: (H, Callable[[H], Iterable[H]]) -> Iterable[H]
    """
    Breadth first traversal of a DAG starting from `start`.

    Parameters
    ----------
    start : H
        A starting node
    expand : (H) -> Iterable[H]
        A function returning children of a node.
    """
    queue = deque([start])
    visited = set()  # type: Set[H]
    while queue:
        item = queue.popleft()
        if item not in visited:
            yield item
            visited.add(item)
            queue.extend(expand(item))


def strongly_connected_components(nodes, expand):
    # type: (Iterable[H], Callable[[H], Iterable[H]]) -> List[List[H]]
    """
    Return a list of strongly connected components.

    Implementation of Tarjan's SCC algorithm.
    """
    # SCC found
    components = []  # type: List[List[H]]
    # node stack in BFS
    stack = []       # type: List[H]
    # == set(stack) : a set of all nodes in stack (for faster lookup)
    stackset = set()

    # node -> int increasing node numbering as encountered in DFS traversal
    index = {}
    # node -> int the lowest node index reachable from a node
    lowlink = {}

    indexgen = itertools.count()

    def push_node(v):
        # type: (H) -> None
        """Push node onto the stack."""
        stack.append(v)
        stackset.add(v)
        index[v] = lowlink[v] = next(indexgen)

    def pop_scc(v):
        # type: (H) -> List[H]
        """Pop from the stack a SCC rooted at node v."""
        i = stack.index(v)
        scc = stack[i:]
        del stack[i:]
        stackset.difference_update(scc)
        return scc

    def isvisited(node):  # type: (H) -> bool
        return node in index

    def strong_connect(v):
        # type: (H) -> None
        push_node(v)

        for w in expand(v):
            if not isvisited(w):
                strong_connect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in stackset:
                lowlink[v] = min(lowlink[v], index[w])

        if index[v] == lowlink[v]:
            scc = pop_scc(v)
            components.append(scc)

    for node in nodes:
        if not isvisited(node):
            strong_connect(node)

    return components
