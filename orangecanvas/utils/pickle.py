import pickle
import importlib
from types import FunctionType
from itertools import chain
from typing import IO, Collection, Callable


class UnsafeUnpicklingError(pickle.UnpicklingError):
    """Raised when an unpickling attempt uses a disallowed class.

    Attributes
    ----------
    name : str
        The fully-qualified name of the disallowed class (``module.ClassName``).
    """

    name: str

    def __init__(self, name: str):
        """Initialize the error with the disallowed class name.

        Parameters
        ----------
        name : str
            The fully-qualified name of the disallowed class.
        """
        super().__init__(f"'{name}' not allowed for unpickling")
        self.name = name


class RestrictedUnpickler(pickle.Unpickler):
    """A :class:`pickle.Unpickler` subclass that restricts unpickling to a whitelist.

    This class prevents arbitrary code execution during unpickling by only
    allowing classes explicitly listed in the ``allowed`` set (or the class-level
    :attr:`EXTRA` list). It is used for safely loading workflow files that may
    have been created or modified by untrusted sources.
    """
    #: Default allowed safe list
    BUILTINS = (
        "builtins:float",
        "builtins:bool",
        "builtins:bytearray",
        "builtins:bytes",
        "builtins:set",
        "builtins:tuple",
        "builtins:dict",
        "builtins:list",
        "builtins:str",
        "builtins:int",
        "builtins:frozenset",
        "builtins:complex",
        "builtins:range",
        "decimal:Decimal",
        "fractions:Fraction",
        "datetime:date",
        "datetime:datetime",
        "datetime:timedelta",
        "collections:deque",
        "collections:defaultdict",
        "collections:OrderedDict",
        "types:SimpleNamespace",
        # abc:ABCMeta is required for Fraction etc.
        "abc:ABCMeta",
    )
    #: Extra default allowed types in addition to basic builtins
    EXTRA = []

    def __init__(self, file, allowed: Collection[str]=None, **kwargs):
        """Initialize the restricted unpickler.

        Parameters
        ----------
        file : IO[bytes]
            A binary file-like object to read pickled data from.
        allowed : Collection[str]
            Additional fully-qualified type names to permit beyond the
            class-level :attr:`EXTRA` list. Each entry must be in the form
            ``"module.ClassName"`` (e.g. ``"my_module.MyClass"``).
        **kwargs
            Additional keyword arguments forwarded to :class:`pickle.Unpickler`.
        """
        super().__init__(file, **kwargs)
        if allowed is None:
            allowed = set()
        allowed = set(allowed) if allowed else set()
        allowed.update(self.BUILTINS)
        allowed.update(self.EXTRA)
        self.allowed = set(allowed)

    def find_class(self, module: str, qualname: str) -> type:
        """Resolve and return the class identified by *module* and *qualname*.

        Only classes whose fully-qualified name (``"{module}:{qualname}"``) is
        present in the allowed set are returned. All other classes raise
        :exc:`UnsafeUnpicklingError`.

        The resolution follows dotted qualnames (e.g. ``"mypackage.submodule.Class"``)
        by importing the top-level module and then walking attributes via
        :func:`getattr`.

        Parameters
        ----------
        module : str
            The module where the class is defined.
        qualname : str
            The qualified name of the class within the module. May contain
            dots for nested classes (e.g. ``"OuterClass.InnerClass"``).

        Returns
        -------
        type
            The resolved class object.

        Raises
        ------
        UnsafeUnpicklingError
            If the class is not in the allowed set.
        """
        fullname = f"{module}:{qualname}"
        if fullname not in self.allowed:
            raise UnsafeUnpicklingError(fullname)

        # Import the top-level module. The ``fromlist`` argument ensures that
        # submodules referenced in a dotted qualname are importable as
        # attributes of the returned module object.
        parts = qualname.split(".")
        mod = importlib.import_module(module)

        # Walk the dotted path to resolve nested classes / attributes.
        obj: object = mod
        for part in parts:
            obj = getattr(obj, part)

        return obj  # type: ignore[return-value]

    @classmethod
    def register_pickle_safe(cls, klass):
        """Register `klass` as a pickle-safe type on the class-level ``EXTRA``
        list.

        This is a convenience method for adding custom classes to the whitelist
        so that they can be unpickled without needing to pass them through the
        ``allowed`` parameter at construction time.

        Parameters
        ----------
        klass : type
            The class to register.
        """
        module_name = getattr(klass, "__module__", None)
        name = getattr(klass, "__qualname__", None)
        if name is None:
            name = getattr(klass, "__name__", None)
        full_name = f"{module_name}:{name}"
        if full_name not in cls.EXTRA:
            cls.EXTRA.append(full_name)
        return klass


def qualname(obj: type | FunctionType) -> str:
    """Return the fully-qualified name of `obj` in `"{module}:{name}"`` format.

    Parameters
    ----------
    obj : type | types.FunctionType
        A class or function object.

    Returns
    -------
    str
        The fully-qualified name, e.g. ``"my_package.mymodule:MyClass"``.
    """
    module_name = getattr(obj, "__module__", None)
    name = getattr(obj, "__qualname__", None)
    if name is None:
        name = getattr(obj, "__name__", None)
    return f"{module_name}:{name}"


class RestrictedPickler(pickle.Pickler):
    """A :class:`pickle.Pickler` subclass that restricts pickling to a whitelist.

    This class prevents pickling of arbitrary objects by intercepting the
    pickling process through :obj:`dispatch_table`. Only built-in types and
    explicitly whitelisted custom types are permitted.
    """

    class DispatchTable(dict):
        """
        A 'pickle' dispatch table restricting serialization to an allowed
        subset.
        """
        #: Allowed classes/names
        allowed: set[str]

        def __init__(self, allowed):
            super().__init__()
            self.allowed = set(allowed)

        def __missing__(self, key: type) -> "Callable[[], None]":
            fullname = f"{key.__module__}:{key.__qualname__}"
            if fullname in self.allowed:
                # Raise KeyError to signal pickle to use the default reducer
                # (e.g. __reduce__ or __reduce_ex__ for the type).
                raise KeyError()
            else:
                # Return a 'reducer' callable that raises an error when invoked.
                def reduce_raise_error(*_args: object) -> None:
                    raise pickle.PicklingError(
                        f"'{key}' is not registered for pickling."
                    )
                return reduce_raise_error

    dispatch_table: DispatchTable

    def __init__(self, file: IO[bytes], allowed: Collection[str] | None = None,
                 **kwargs) -> None:
        """Initialize the restricted pickler.

        Parameters
        ----------
        file : IO[bytes]
            A binary file-like object to write pickled data to.
        allowed : Collection[str] | None
            Fully-qualified type names (e.g. ``"my_module:MyClass"``) that are
            permitted for pickling. If ``None``, no custom types are allowed
            beyond built-in types.
        **kwargs
            Additional keyword arguments forwarded to
            :class:`pickle.Pickler`.
        """
        super().__init__(file, **kwargs)
        self.allowed = set(allowed) if allowed else set()
        self.dispatch_table = RestrictedPickler.DispatchTable(
            chain(RestrictedUnpickler.BUILTINS, RestrictedUnpickler.EXTRA, self.allowed)
        )
