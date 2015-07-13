"""
"""
import sys

from types import ModuleType


def make_module(name, package="", **namespace):
    mod = ModuleType(name)
    mod.__package__ = package or ""
    if package:
        mod.__name__ = "{}.{}".format(package, name)
    else:
        mod.__name = name
    mod.__dict__.update(namespace)
    return mod

Test = make_module(
    "Test", __package__,
    NAME="Test",
    DESCRIPTION="This is a test.",
    LONG_DESCRIPTION="This. Is. A. Test.",
    PRIORITY=3
)
Test.__path__ = []


constants = make_module(
    "constants", __package__, NAME="Constants"
)
constants.__path__ = []

constants.zero = make_module(
    "zero", constants.__name__,
    NAME="Zero",
    OUTPUTS=[("value", int)],
    CATEGORY="Constants",
    zero=None,
)

constants.one = make_module(
    "one", constants.__name__,
    NAME="One",
    OUTPUTS=[("value", int)],
    CATEGORY="Constants",
    one=None,
)

operators = make_module(
    "operators", __package__, NAME="Operators"
)
operators.__path__ = []

operators.add = make_module(
    "add", operators.__name__,
    NAME="Add",
    INPUTS=[("left", int, "set_left"),
            ("right", int, "set_right")],
    OUTPUTS=[("value", int)],
    CATEGORY="Operators",
    add=None
)

operators.sub = make_module(
    "sub", operators.__name__,
    NAME="Subtract",
    INPUTS=[("left", int, "set_left"),
            ("right", int, "set_right")],
    OUTPUTS=[("value", int)],
    CATEGORY="Operators",
    sub=None,
)

operators.mult = make_module(
    "mult", operators.__name__,
    NAME="Multiply",
    INPUTS=[("left", int, "set_left"),
            ("right", int, "set_right")],
    OUTPUTS=[("value", int)],
    CATEGORY="Operators",
    mult=None,
)

operators.div = make_module(
    "div", operators.__name__,
    NAME="Divide",
    INPUTS=[("left", int, "set_left"),
            ("right", int, "set_right")],
    OUTPUTS=[("value", int)],
    CATEGORY="Operators",
    div=None
)


def set_up_package(package):
    sys.modules[package.__name__] = package
    for val in package.__dict__.values():
        if isinstance(val, ModuleType):
            sys.modules[val.__name__] = val


def tear_down_package(package):
    for val in package.__dict__.values():
        if isinstance(val, ModuleType):
            if val.__name__ in sys.modules:
                del sys.modules[val.__name__]
    if package.__name__ in sys.modules:
        del sys.modules[package.__name__]


def set_up_modules():
    set_up_package(constants)
    set_up_package(operators)


def tear_down_modules():
    tear_down_package(constants)
    tear_down_package(operators)


def small_testing_registry():
    """Return a small registry with a few widgets for testing.
    """
    from ..description import (
        WidgetDescription, CategoryDescription, InputSignal, OutputSignal
    )
    from .. import WidgetRegistry

    registry = WidgetRegistry()

    const_cat = CategoryDescription(
        "Constants", background="light-orange")

    zero = WidgetDescription(
        "zero", "zero", "Constants",
        qualified_name="zero",
        package=__package__,
        outputs=[OutputSignal("value", "int")])

    one = WidgetDescription(
        "one", "one", "Constants",
        qualified_name="one",
        package=__package__,
        outputs=[OutputSignal("value", "int")])

    unit = WidgetDescription(
        "unit", "unit", "Constants",
        qualified_name="unit",
        package=__package__,
        outputs=[OutputSignal("value", "tuple")])

    op_cat = CategoryDescription(
        "Operators", background="grass")

    add = WidgetDescription(
        "add", "add", "Operators",
        qualified_name="add",
        package=__package__,
        inputs=[InputSignal("left", "int", "set_left"),
                InputSignal("right", "int", "set_right")],
        outputs=[OutputSignal("result", "int")]
    )
    sub = WidgetDescription(
        "sub", "sub", "Operators",
        qualified_name="sub",
        package=__package__,
        inputs=[InputSignal("left", "int", "set_left"),
                InputSignal("right", "int", "set_right")],
        outputs=[OutputSignal("result", "int")]
    )
    mult = WidgetDescription(
        "mult", "mult", "Operators",
        qualified_name="mult",
        package=__package__,
        inputs=[InputSignal("left", "int", "set_left"),
                InputSignal("right", "int", "set_right")],
        outputs=[OutputSignal("result", "int")]
    )
    div = WidgetDescription(
        "div", "div", "Operators",
        qualified_name="div",
        package=__package__,
        inputs=[InputSignal("left", "int", "set_left"),
                InputSignal("right", "int", "set_right")],
        outputs=[OutputSignal("result", "int")]
    )
    negate = WidgetDescription(
        "negate", "negate", "Operators",
        qualified_name="negate",
        package=__package__,
        inputs=[InputSignal("value", "int", "set_value")],
        outputs=[OutputSignal("result", "int")],
    )
    struct_cat = CategoryDescription(
        "Structure", background="red")

    cons = WidgetDescription(
        "cons", "cons", "Structure",
        qualified_name="cons",
        package=__package__,
        inputs=[InputSignal("first", "object", "set_first"),
                InputSignal("second", "object", "set_second")],
        outputs=[OutputSignal("cons", "tuple")]
    )
    decons = WidgetDescription(
        "decons", "decons", "Structure",
        qualified_name="decons",
        package=__package__,
        inputs=[InputSignal("cons", "tuple", "set_cons")],
        outputs=[OutputSignal("first", "object", doc="First matched"),
                 OutputSignal("second", "object", doc="Second matched"),
                 OutputSignal("empty", "tuple", doc="No match")]
    )

    registry.register_category(const_cat)
    registry.register_category(op_cat)
    registry.register_category(struct_cat)

    registry.register_widget(zero)
    registry.register_widget(one)
    registry.register_widget(unit)
    registry.register_widget(add)
    registry.register_widget(sub)
    registry.register_widget(mult)
    registry.register_widget(div)
    registry.register_widget(negate)

    registry.register_widget(cons)
    registry.register_widget(decons)

    return registry
