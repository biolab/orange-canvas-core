# Module-level classes for testing pickling round-trips
import io
import pickle
import unittest
from collections import deque, defaultdict, OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

from orangecanvas.utils.pickle import RestrictedUnpickler, UnsafeUnpicklingError, RestrictedPickler, qualname


class _TestPickleClass:
    """Test class with ``__reduce__`` for pickle round-trip tests."""
    def __init__(self, value):
        self.value = value

    def __reduce__(self):
        return (_TestPickleClass, (self.value,))

    def __eq__(self, other):
        return isinstance(other, _TestPickleClass) and self.value == other.value


class _NoReduceClass:
    """Test class without custom ``__reduce__`` for pickling block tests."""
    def __init__(self, value):
        self.value = value


class TestRestrictedUnpickle(unittest.TestCase):
    """Tests for RestrictedUnpickler security and functionality."""

    def _pickle_to_bytes(self, obj):
        """Helper to pickle an object to bytes."""
        buf = io.BytesIO()
        pickle.dump(obj, buf)
        buf.seek(0)
        return buf.read()

    # -- Allowed built-in types --

    def test_unpickle_frozenset(self):
        """Allowed built-in: frozenset."""
        data = self._pickle_to_bytes(frozenset([1, 2, 3]))
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(result, frozenset([1, 2, 3]))

    def test_unpickle_complex(self):
        """Allowed built-in: complex."""
        data = self._pickle_to_bytes(complex(1, 2))
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(result, complex(1, 2))

    def test_unpickle_range(self):
        """Allowed built-in: range."""
        data = self._pickle_to_bytes(range(10))
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(list(result), list(range(10)))

    def test_unpickle_decimal(self):
        """Allowed built-in: decimal.Decimal."""
        data = self._pickle_to_bytes(Decimal("3.14"))
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(result, Decimal("3.14"))

    def test_unpickle_fraction(self):
        """Allowed built-in: fractions.Fraction."""
        data = self._pickle_to_bytes(Fraction(1, 3))
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(result, Fraction(1, 3))

    def test_unpickle_date(self):
        """Allowed built-in: datetime.date."""
        data = self._pickle_to_bytes(date(2024, 1, 15))
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(result, date(2024, 1, 15))

    def test_unpickle_datetime(self):
        """Allowed built-in: datetime.datetime."""
        data = self._pickle_to_bytes(datetime(2024, 1, 15, 10, 30))
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(result, datetime(2024, 1, 15, 10, 30))

    def test_unpickle_timedelta(self):
        """Allowed built-in: datetime.timedelta."""
        data = self._pickle_to_bytes(timedelta(days=1, hours=2))
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(result, timedelta(days=1, hours=2))

    def test_unpickle_deque(self):
        """Allowed built-in: collections.deque."""
        data = self._pickle_to_bytes(deque([1, 2, 3]))
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(list(result), [1, 2, 3])

    def test_unpickle_defaultdict(self):
        """Allowed built-in: collections.defaultdict."""
        data = self._pickle_to_bytes(defaultdict(int, {"a": 1}))
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(dict(result), {"a": 1})

    def test_unpickle_ordered_dict(self):
        """Allowed built-in: collections.OrderedDict."""
        data = self._pickle_to_bytes(OrderedDict([("b", 2), ("a", 1)]))
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(list(result.keys()), ["b", "a"])

    def test_unpickle_simple_namespace(self):
        """Allowed built-in: types.SimpleNamespace."""
        data = self._pickle_to_bytes(SimpleNamespace(x=1, y=2))
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(result.x, 1)
        self.assertEqual(result.y, 2)

    # -- Disallowed types --

    def test_unpickle_os_system_blocked(self):
        """Disallowed: os.system should raise UnsafeUnpicklingError."""
        import os
        data = self._pickle_to_bytes(os.system)
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        with self.assertRaises(UnsafeUnpicklingError) as ctx:
            unpickler.load()
        self.assertIn(":system", ctx.exception.name)

    def test_unpickle_subprocess_blocked(self):
        """Disallowed: subprocess.Popen should raise UnsafeUnpicklingError."""
        import subprocess
        data = self._pickle_to_bytes(subprocess.Popen)
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        with self.assertRaises(UnsafeUnpicklingError) as ctx:
            unpickler.load()
        self.assertIn("subprocess", ctx.exception.name)

    def test_unpickle_builtin_dict_allowed(self):
        """Built-in dict is allowed via pickle dispatch table."""
        data = self._pickle_to_bytes({"key": "value"})
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(result, {"key": "value"})

    def test_unpickle_builtin_list_allowed(self):
        """Built-in list is allowed via pickle dispatch table."""
        data = self._pickle_to_bytes([1, 2, 3])
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(result, [1, 2, 3])

    def test_unpickle_builtin_str_allowed(self):
        """Built-in str is allowed via pickle dispatch table."""
        data = self._pickle_to_bytes("hello world")
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(result, "hello world")

    def test_unpickle_builtin_int_allowed(self):
        """Built-in int is allowed via pickle dispatch table."""
        data = self._pickle_to_bytes(42)
        unpickler = RestrictedUnpickler(io.BytesIO(data))
        result = unpickler.load()
        self.assertEqual(result, 42)

    # -- Custom allowed types --

    def test_unpickle_custom_allowed_type(self):
        """Custom types can be added via the allowed parameter."""
        obj = _TestPickleClass(123)
        data = self._pickle_to_bytes(obj)

        allowed = {f"{__name__}:_TestPickleClass"}
        unpickler = RestrictedUnpickler(io.BytesIO(data), allowed=allowed)
        result = unpickler.load()
        self.assertEqual(result.value, 123)

    def test_unpickle_custom_disallowed_type(self):
        """Custom types not in allowed set should raise error."""
        # Use a module-level class that's not in the allowed set
        obj = _TestPickleClass(456)
        data = self._pickle_to_bytes(obj)

        # Try to unpickle with a different allowed set (not containing _TestPickleClass)
        allowed = {"test_pickle:DifferentClass"}
        unpickler = RestrictedUnpickler(io.BytesIO(data), allowed=allowed)
        with self.assertRaises(UnsafeUnpicklingError):
            unpickler.load()

    # -- register_pickle_safe --

    def test_register_pickle_safe(self):
        """register_pickle_safe adds a class to EXTRA."""
        original_len = len(RestrictedUnpickler.EXTRA)

        RestrictedUnpickler.register_pickle_safe(_TestPickleClass)

        try:
            # Check that the class was registered
            found = any("_TestPickleClass" in entry for entry in RestrictedUnpickler.EXTRA)
            self.assertTrue(found, f"_TestPickleClass not in EXTRA: {RestrictedUnpickler.EXTRA}")

            # Should be unpicklable without explicit allowed set
            obj = _TestPickleClass(789)
            data = self._pickle_to_bytes(obj)
            unpickler = RestrictedUnpickler(io.BytesIO(data))
            result = unpickler.load()
            self.assertEqual(result.value, 789)
        finally:
            # Restore original EXTRA list
            RestrictedUnpickler.EXTRA = RestrictedUnpickler.EXTRA[:original_len]


class TestRestrictedPickle(unittest.TestCase):
    """Tests for RestrictedPickler security and functionality."""

    def _pickle_with_restricted(self, obj, allowed=None):
        """Helper to pickle an object with RestrictedPickler."""
        buf = io.BytesIO()
        pickler = RestrictedPickler(buf, allowed=allowed)
        pickler.dump(obj)
        return buf.getvalue()

    def _unpickle_standard(self, data):
        """Helper to unpickle with standard pickle.Unpickler."""
        return pickle.loads(data)

    # -- Allowed built-in types --

    def test_pickle_builtin_int(self):
        """Built-in int can be pickled."""
        data = self._pickle_with_restricted(42)
        result = self._unpickle_standard(data)
        self.assertEqual(result, 42)

    def test_pickle_builtin_str(self):
        """Built-in str can be pickled."""
        data = self._pickle_with_restricted("hello")
        result = self._unpickle_standard(data)
        self.assertEqual(result, "hello")

    def test_pickle_builtin_list(self):
        """Built-in list can be pickled."""
        data = self._pickle_with_restricted([1, 2, 3])
        result = self._unpickle_standard(data)
        self.assertEqual(result, [1, 2, 3])

    def test_pickle_builtin_dict(self):
        """Built-in dict can be pickled."""
        data = self._pickle_with_restricted({"a": 1})
        result = self._unpickle_standard(data)
        self.assertEqual(result, {"a": 1})

    def test_pickle_builtin_tuple(self):
        """Built-in tuple can be pickled."""
        data = self._pickle_with_restricted((1, 2, 3))
        result = self._unpickle_standard(data)
        self.assertEqual(result, (1, 2, 3))

    def test_pickle_builtin_frozenset(self):
        """Built-in frozenset can be pickled."""
        data = self._pickle_with_restricted(frozenset([1, 2]))
        result = self._unpickle_standard(data)
        self.assertEqual(result, frozenset([1, 2]))

    def test_pickle_builtin_complex(self):
        """Built-in complex can be pickled."""
        data = self._pickle_with_restricted(complex(1, 2))
        result = self._unpickle_standard(data)
        self.assertEqual(result, complex(1, 2))

    def test_pickle_builtin_range(self):
        """Built-in range can be pickled."""
        data = self._pickle_with_restricted(range(5))
        result = self._unpickle_standard(data)
        self.assertEqual(list(result), list(range(5)))

    def test_pickle_builtin_decimal(self):
        """Built-in Decimal can be pickled."""
        data = self._pickle_with_restricted(Decimal("3.14"))
        result = self._unpickle_standard(data)
        self.assertEqual(result, Decimal("3.14"))

    def test_pickle_builtin_fraction(self):
        """Built-in Fraction can be pickled."""
        data = self._pickle_with_restricted(Fraction(2, 3))
        result = self._unpickle_standard(data)
        self.assertEqual(result, Fraction(2, 3))

    # -- Disallowed custom types --

    def test_pickle_custom_type_blocked(self):
        """Custom types without explicit allow should raise PicklingError."""
        obj = _TestPickleClass("secret")
        with self.assertRaises(pickle.PicklingError):
            self._pickle_with_restricted(obj)

    def test_pickle_custom_type_without_reduce_blocked(self):
        """Custom types without __reduce__ and not in allowed should raise PicklingError."""
        obj = _NoReduceClass(42)
        with self.assertRaises(pickle.PicklingError):
            self._pickle_with_restricted(obj)

    def test_pickle_custom_type_not_in_allowed(self):
        """Custom types not in allowed set should raise PicklingError."""
        obj = _TestPickleClass(1)
        with self.assertRaises(pickle.PicklingError):
            self._pickle_with_restricted(obj, allowed={"test_pickle:DifferentClass"})

    # -- Custom allowed types --

    def test_pickle_custom_allowed_type(self):
        """Custom types in allowed set can be pickled."""
        obj = _TestPickleClass(999)
        allowed = {f"{__name__}:_TestPickleClass"}
        data = self._pickle_with_restricted(obj, allowed=allowed)
        result = self._unpickle_standard(data)
        self.assertEqual(result.value, 999)

    def test_pickle_custom_allowed_type_roundtrip(self):
        """Round-trip: pickle with RestrictedPickler, unpickle with RestrictedUnpickler."""
        obj = _TestPickleClass(42)
        allowed = {f"{__name__}:_TestPickleClass"}

        pick_buf = io.BytesIO()
        pickler = RestrictedPickler(pick_buf, allowed=allowed)
        pickler.dump(obj)
        data = pick_buf.getvalue()

        unpickler = RestrictedUnpickler(io.BytesIO(data), allowed=allowed)
        result = unpickler.load()

        self.assertEqual(result.value, 42)

    # -- Nested structures --

    def test_pickle_nested_builtin(self):
        """Nested built-in structures can be pickled."""
        data = self._pickle_with_restricted({
            "numbers": [1, 2, 3],
            "mapping": OrderedDict([("z", 26), ("a", 1)]),
            "special": Decimal("1.5"),
        })
        result = self._unpickle_standard(data)
        self.assertEqual(result["numbers"], [1, 2, 3])
        self.assertEqual(list(result["mapping"].keys()), ["z", "a"])
        self.assertEqual(result["special"], Decimal("1.5"))

    def test_pickle_empty_collections(self):
        """Empty collections can be pickled."""
        data = self._pickle_with_restricted({
            "list": [],
            "dict": {},
            "set": set(),
            "frozenset": frozenset(),
            "tuple": (),
        })
        result = self._unpickle_standard(data)
        self.assertEqual(result["list"], [])
        self.assertEqual(result["dict"], {})
        self.assertEqual(result["set"], set())
        self.assertEqual(result["frozenset"], frozenset())
        self.assertEqual(result["tuple"], ())


class TestQualname(unittest.TestCase):
    """Tests for the qualname helper function."""

    def test_qualname(self):
        q = qualname(dict)
        self.assertEqual(q, "builtins:dict")
        q = qualname(list)
        self.assertEqual(q, "builtins:list")
        q = qualname(_TestPickleClass)
        self.assertTrue(q.endswith(":_TestPickleClass"))
        q = qualname(len)
        self.assertEqual(q, "builtins:len")