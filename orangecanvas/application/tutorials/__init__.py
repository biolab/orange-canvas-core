"""
Orange Canvas Tutorial schemes

"""
import os
import logging
import types

import six
import pkg_resources

from orangecanvas import config

log = logging.getLogger(__name__)


def list_workflows(package):
    # type: (types.ModuleType) -> List[str]
    """
    Return a list of .ows files in the located next to `package`.
    """

    def is_ows(filename):
        return filename.endswith(".ows")

    resources = pkg_resources.resource_listdir(package.__name__, ".")
    resources = filter(is_ows, resources)
    return sorted(resources)


def tutorials():
    """
    Return all known example workflows.
    """
    all_tutorials = []
    for ep in config.default.tutorials_entry_points():
        tutorials = None
        try:
            tutorials = ep.resolve()
        except pkg_resources.DistributionNotFound as ex:
            log.warning("Could not load examples from %r (%r)",
                        ep.dist, ex)
            continue
        except ImportError:
            log.error("Could not load tutorials from %r",
                      ep.dist, exc_info=True)
            continue
        except Exception:
            log.error("Could not load tutorials from %r",
                      ep.dist, exc_info=True)
            continue

        if isinstance(tutorials, types.ModuleType):
            package = tutorials
            tutorials = list_workflows(tutorials)
            tutorials = [ExampleWorkflow(t, package, ep.dist)
                         for t in tutorials]
        elif isinstance(tutorials, (types.FunctionType, types.MethodType)):
            try:
                tutorials = tutorials()
            except Exception as ex:
                log.error("A callable entry point (%r) raised an "
                          "unexpected error.",
                          ex, exc_info=True)
                continue
            tutorials = [ExampleWorkflow(t, package=None, distribution=ep.dist)
                         for t in tutorials]

        all_tutorials.extend(tutorials)

    return all_tutorials


class ExampleWorkflow(object):
    def __init__(self, resource, package=None, distribution=None):
        self.resource = resource
        self.package = package
        self.distribution = distribution

    def abspath(self):
        """
        Return absolute filename for the workflow if possible else
        raise an ValueError.
        """
        if self.package is not None:
            return pkg_resources.resource_filename(self.package.__name__,
                                                   self.resource)
        elif isinstance(self.resource, six.string_types):
            if os.path.isabs(self.resource):
                return self.resource

        raise ValueError("cannot resolve resource to an absolute name")

    def stream(self):
        """Return the tutorial file as an open stream.
        """
        if self.package is not None:
            return pkg_resources.resource_stream(self.package.__name__,
                                                 self.resource)
        elif isinstance(self.resource, six.string_types):
            if os.path.isabs(self.resource) and os.path.exists(self.resource):
                return open(self.resource, "rb")

        raise ValueError
