"""
Widget Discovery Utilities
==========================

"""
import sys

import six

from .description import (
    WidgetDescription, WidgetSpecificationError,
    CategoryDescription, CategorySpecificationError,
    InputSignal, input_channel_from_args,
    OutputSignal, output_channel_from_args
)


def widget_from_module_globals(module):
    """
    Get the :class:`WidgetDescription` by inspecting the `module`'s
    global namespace.

    The module is inspected for global variables (upper case versions of
    :class:`WidgetDescription` parameters, i.e. NAME global variable is used
    as a `name` parameter).

    Parameters
    ----------
    module : `module` or str
        A module to inspect for widget description. Can be passed
        as a string (a qualified import name).

    """
    if isinstance(module, six.string_types):
        module = __import__(module, fromlist=[""])

    module_name = module.__name__.rsplit(".", 1)[-1]
    if module.__package__:
        package_name = module.__package__.rsplit(".", 1)[-1]
    else:
        package_name = None

    # Default widget class name unless otherwise specified is the
    # module name, and default category the package name
    default_cls_name = module_name
    default_cat_name = package_name if package_name else ""

    widget_cls_name = getattr(module, "WIDGET_CLASS", default_cls_name)
    try:
        widget_class = getattr(module, widget_cls_name)
        name = getattr(module, "NAME")
    except AttributeError:
        # The module does not have a widget class implementation or the
        # widget name.
        raise WidgetSpecificationError

    qualified_name = "%s.%s" % (module.__name__, widget_class.__name__)

    id = getattr(module, "ID", module_name)
    inputs = getattr(module, "INPUTS", [])
    outputs = getattr(module, "OUTPUTS", [])
    category = getattr(module, "CATEGORY", default_cat_name)
    version = getattr(module, "VERSION", None)
    description = getattr(module, "DESCRIPTION", name)
    long_description = getattr(module, "LONG_DESCRIPTION", None)
    author = getattr(module, "AUTHOR", None)
    author_email = getattr(module, "AUTHOR_EMAIL", None)
    maintainer = getattr(module, "MAINTAINER", None)
    maintainer_email = getattr(module, "MAINTAINER_EMAIL", None)
    help = getattr(module, "HELP", None)
    help_ref = getattr(module, "HELP_REF", None)
    url = getattr(module, "URL", None)

    icon = getattr(module, "ICON", None)
    priority = getattr(module, "PRIORITY", sys.maxsize)
    keywords = getattr(module, "KEYWORDS", None)
    background = getattr(module, "BACKGROUND", None)
    replaces = getattr(module, "REPLACES", None)

    inputs = list(map(input_channel_from_args, inputs))
    outputs = list(map(output_channel_from_args, outputs))

    # Convert all signal types into qualified names.
    # This is to prevent any possible import problems when cached
    # descriptions are unpickled (the relevant code using this lists
    # should be able to handle missing types better).
    for s in inputs + outputs:
        s.type = "%s.%s" % (s.type.__module__, s.type.__name__)

    return WidgetDescription(
        name=name,
        id=id,
        category=category,
        version=version,
        description=description,
        long_description=long_description,
        qualified_name=qualified_name,
        package=module.__package__,
        inputs=inputs,
        outputs=outputs,
        author=author,
        author_email=author_email,
        maintainer=maintainer,
        maintainer_email=maintainer_email,
        help=help,
        help_ref=help_ref,
        url=url,
        keywords=keywords,
        priority=priority,
        icon=icon,
        background=background,
        replaces=replaces)


def category_from_package_globals(package):
    """
    Get the :class:`CategoryDescription` from a package.

    The package global namespace is inspected for global variables
    (upper case versions of :class:`CategoryDescription` parameters)

    Parameters
    ----------
    package : `module` or `str`
        A package containing the category. Can be passed
        as a string (qualified import name).

    """
    if isinstance(package, six.string_types):
        package = __import__(package, fromlist=[""])

    package_name = package.__name__
    qualified_name = package_name
    default_name = package_name.rsplit(".", 1)[-1]

    name = getattr(package, "NAME", default_name)
    description = getattr(package, "DESCRIPTION", None)
    long_description = getattr(package, "LONG_DESCRIPTION", None)
    author = getattr(package, "AUTHOR", None)
    author_email = getattr(package, "AUTHOR_EMAIL", None)
    maintainer = getattr(package, "MAINTAINER", None)
    maintainer_email = getattr(package, "MAINTAINER_MAIL", None)
    url = getattr(package, "URL", None)
    help = getattr(package, "HELP", None)
    keywords = getattr(package, "KEYWORDS", None)
    widgets = getattr(package, "WIDGETS", None)
    priority = getattr(package, "PRIORITY", sys.maxsize - 1)
    icon = getattr(package, "ICON", None)
    background = getattr(package, "BACKGROUND", None)
    hidden = getattr(package, "HIDDEN", None)

    if priority == sys.maxsize - 1 and name.lower() == "prototypes":
        priority = sys.maxsize

    return CategoryDescription(
        name=name,
        qualified_name=qualified_name,
        description=description,
        long_description=long_description,
        help=help,
        author=author,
        author_email=author_email,
        maintainer=maintainer,
        maintainer_email=maintainer_email,
        url=url,
        keywords=keywords,
        widgets=widgets,
        priority=priority,
        icon=icon,
        background=background,
        hidden=hidden)
