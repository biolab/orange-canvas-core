"""
Widget meta description classes
===============================

"""

import sys
import copy
import warnings
from typing import Union

from orangecanvas.utils import qualified_name

# Exceptions


class DescriptionError(Exception):
    pass


class WidgetSpecificationError(DescriptionError):
    pass


class SignalSpecificationError(DescriptionError):
    pass


class CategorySpecificationError(DescriptionError):
    pass


###############
# Channel flags
###############

# A single signal
Single = 2

# Multiple signal (more then one input on the channel)
Multiple = 4

# Default signal (default or primary input/output)
Default = 8
NonDefault = 16

# Explicit - only connected if specifically requested or the only possibility
Explicit = 32

# Dynamic type output signal
Dynamic = 64


# Input/output signal (channel) description


class InputSignal(object):
    """
    Description of an input channel.

    Parameters
    ----------
    name : str
        Name of the channel.
    type : str or `type`
        Type of the accepted signals.
    handler : str
        Name of the handler method for the signal.
    flags : int, optional
        Channel flags.
    id : str
        A unique id of the input signal.
    doc : str, optional
        A docstring documenting the channel.
    replaces : List[str]
        A list of names this input replaces.
    """
    def __init__(self, name, type, handler, flags=Single + NonDefault,
                 id=None, doc=None, replaces=[]):
        self.name = name
        self.type = type
        self.handler = handler
        self.id = id
        self.doc = doc
        self.replaces = list(replaces)

        if not (flags & Single or flags & Multiple):
            flags += Single

        if not (flags & Default or flags & NonDefault):
            flags += NonDefault

        self.single = flags & Single
        self.default = flags & Default
        self.explicit = flags & Explicit
        self.flags = flags

    def __str__(self):
        fmt = ("{0.__name__}(name={name!r}, type={type!s}, "
               "handler={handler}, ...)")
        return fmt.format(type(self), **self.__dict__)

    __repr__ = __str__


def input_channel_from_args(args):
    if isinstance(args, tuple):
        return InputSignal(*args)
    elif isinstance(args, dict):
        return InputSignal(**args)
    elif isinstance(args, InputSignal):
        return copy.copy(args)
    else:
        raise TypeError("tuple, dict or InputSignal expected "
                        "(got {0!r})".format(type(args)))


class OutputSignal(object):
    """
    Description of an output channel.

    Parameters
    ----------
    name : str
        Name of the channel.
    type : str or `type`
        Type of the output signals.
    flags : int, optional
        Channel flags.
    id : str
        A unique id of the output signal.
    doc : str, optional
        A docstring documenting the channel.
    replaces : List[str]
        A list of names this output replaces.
    """
    def __init__(self, name, type, flags=Single + NonDefault,
                 id=None, doc=None, replaces=[]):
        self.name = name
        self.type = type
        self.id = id
        self.doc = doc
        self.replaces = list(replaces)

        if not (flags & Single or flags & Multiple):
            flags += Single

        if not (flags & Default or flags & NonDefault):
            flags += NonDefault

        self.single = flags & Single
        self.default = flags & Default
        self.explicit = flags & Explicit
        self.dynamic = flags & Dynamic
        self.flags = flags

        if self.dynamic and not self.single:
            raise SignalSpecificationError(
                "Output signal can not be 'Multiple' and 'Dynamic'."
                )

    def __str__(self):
        fmt = ("{0.__name__}(name={name!r}, type={type!s}, "
               "...)")
        return fmt.format(type(self), **self.__dict__)

    __repr__ = __str__


def output_channel_from_args(args):
    if isinstance(args, tuple):
        return OutputSignal(*args)
    elif isinstance(args, dict):
        return OutputSignal(**args)
    elif isinstance(args, OutputSignal):
        return copy.copy(args)
    else:
        raise TypeError("tuple, dict or OutputSignal expected "
                        "(got {0!r})".format(type(args)))


def normalize_type(type_):
    # type: (Union[type, str]) -> str
    if isinstance(type_, type):
        return qualified_name(type_)
    elif isinstance(type_, str):
        return type_
    else:
        raise TypeError


class WidgetDescription(object):
    """
    Description of a widget.

    Parameters
    ----------
    name : str
        A human readable name of the widget.
    id : str
        A unique identifier of the widget (in most situations this should
        be the full module name).
    category : str, optional
        A name of the category in which this widget belongs.
    version : str, optional
        Version of the widget. By default the widget inherits the project
        version.
    description : str, optional
        A short description of the widget, suitable for a tool tip.
    long_description : str, optional
        A longer description of the widget, suitable for a 'what's this?'
        role.
    qualified_name : str
        A qualified name (import name) of the class implementing the widget.
    package : str, optional
        A package name where the widget is implemented.
    project_name : str, optional
        The distribution name that provides the widget.
    inputs : list of :class:`InputSignal`
        A list of input channels provided by the widget.
    outputs : list of :class:`OutputSignal`
        A list of output channels provided by the widget.
    help : str, optional
        URL or an Resource template of a detailed widget help page.
    help_ref : str, optional
        A text reference id that can be used to identify the help
        page, for instance an intersphinx reference.
    author : str, optional
        Author name.
    author_email : str, optional
        Author email address.
    maintainer : str, optional
        Maintainer name
    maintainer_email : str, optional
        Maintainer email address.
    keywords : list-of-str, optional
        A list of keyword phrases.
    priority : int, optional
        Widget priority (the order of the widgets in a GUI presentation).
    icon : str, optional
        A filename of the widget icon (in relation to the package).
    background : str, optional
        Widget's background color (in the canvas GUI).
    replaces : list of `str`, optional
        A list of ids this widget replaces (optional).

    """
    def __init__(self, name, id, category=None, version=None,
                 description=None, long_description=None,
                 qualified_name=None, package=None, project_name=None,
                 inputs=[], outputs=[],
                 author=None, author_email=None,
                 maintainer=None, maintainer_email=None,
                 help=None, help_ref=None, url=None, keywords=None,
                 priority=sys.maxsize,
                 icon=None, background=None,
                 replaces=None,
                 ):

        if not qualified_name:
            # TODO: Should also check that the name is real.
            raise ValueError("'qualified_name' must be supplied.")

        self.name = name
        self.id = id
        self.category = category
        self.version = version
        self.description = description
        self.long_description = long_description
        self.qualified_name = qualified_name
        self.package = package
        self.project_name = project_name
        # Copy input/outputs and normalize the type to string.
        inputs = [
            InputSignal(
                i.name, normalize_type(i.type), i.handler, i.flags, i.id,
                i.doc, i.replaces
            )
            for i in inputs
        ]
        outputs = [
            OutputSignal(
                o.name, normalize_type(o.type), o.flags, o.id, o.doc,
                o.replaces
            )
            for o in outputs
        ]
        self.inputs = inputs
        self.outputs = outputs
        self.help = help
        self.help_ref = help_ref
        self.author = author
        self.author_email = author_email
        self.maintainer = maintainer
        self.maintainer_email = maintainer_email
        self.url = url
        self.keywords = keywords
        self.priority = priority
        self.icon = icon
        self.background = background
        self.replaces = replaces

    def __str__(self):
        return ("WidgetDescription(name=%(name)r, id=%(id)r), "
                "category=%(category)r, ...)") % self.__dict__

    def __repr__(self):
        return self.__str__()

    @classmethod
    def from_module(cls, module):
        warnings.warn(
            "'WidgetDescription.from_module' is deprecated",
            PendingDeprecationWarning, stacklevel=2
        )
        from .utils import widget_from_module_globals
        return widget_from_module_globals(module)


class CategoryDescription(object):
    """
    Description of a widget category.

    Parameters
    ----------

    name : str
        A human readable name.
    version : str, optional
        Version string.
    description : str, optional
        A short description of the category, suitable for a tool tip.
    long_description : str, optional
        A longer description.
    qualified_name : str,
        Qualified name
    project_name : str
        A project name providing the category.
    priority : int
        Priority (order in the GUI).
    icon : str
        An icon filename (a resource name retrievable using `pkg_resources`
        relative to `qualified_name`).
    background : str
        An background color for widgets in this category.
    hidden : bool
        Is this category (by default) hidden in the canvas gui.

    """
    def __init__(self, name=None, version=None,
                 description=None, long_description=None,
                 qualified_name=None, package=None,
                 project_name=None, author=None, author_email=None,
                 maintainer=None, maintainer_email=None,
                 url=None, help=None, keywords=None,
                 widgets=None, priority=sys.maxsize,
                 icon=None, background=None, hidden=False
                 ):

        self.name = name
        self.version = version
        self.description = description
        self.long_description = long_description
        self.qualified_name = qualified_name
        self.package = package
        self.project_name = project_name
        self.author = author
        self.author_email = author_email
        self.maintainer = maintainer
        self.maintainer_email = maintainer_email
        self.url = url
        self.help = help
        self.keywords = keywords
        self.widgets = widgets or []
        self.priority = priority
        self.icon = icon
        self.background = background
        self.hidden = hidden

    def __str__(self):
        return "CategoryDescription(name=%(name)r, ...)" % self.__dict__

    def __repr__(self):
        return self.__str__()

    @classmethod
    def from_package(cls, package):
        warnings.warn(
            "'CategoryDescription.from_package' is deprecated",
            DeprecationWarning, stacklevel=2
        )
        from .utils import category_from_package_globals
        return category_from_package_globals(package)
