"""
Example workflows discovery.
"""
import os
import logging
import types

import pkg_resources

from orangecanvas import config as _config

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


def workflows(config=None):
    """
    Return all known example workflows.
    """
    if config is None:
        config = _config.default

    workflows = []
    if hasattr(config, "tutorials_entry_points") and \
            callable(config.tutorials_entry_points):
        # back compatibility
        examples_entry_points = config.tutorials_entry_points
    else:
        examples_entry_points = config.examples_entry_points
    for ep in examples_entry_points():
        try:
            examples = ep.resolve()
        except pkg_resources.DistributionNotFound as ex:
            log.warning("Could not load examples from %r (%r)",
                        ep.dist, ex)
            continue
        except Exception:
            log.error("Could not load examples from %r",
                      ep.dist, exc_info=True)
            continue

        if isinstance(examples, types.ModuleType):
            package = examples
            examples = [ExampleWorkflow(t, package, ep.dist)
                        for t in list_workflows(package)]
        elif isinstance(examples, (types.FunctionType, types.MethodType)):
            try:
                examples = examples()
            except Exception as ex:
                log.error("A callable entry point (%r) raised an "
                          "unexpected error.",
                          ex, exc_info=True)
                continue
            examples = [ExampleWorkflow(t, package=None, distribution=ep.dist)
                        for t in examples]
        workflows.extend(examples)
    return workflows


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
        elif isinstance(self.resource, str):
            if os.path.isabs(self.resource):
                return self.resource

        raise ValueError("cannot resolve resource to an absolute name")

    def stream(self):
        """Return the example file as an open stream.
        """
        if self.package is not None:
            return pkg_resources.resource_stream(self.package.__name__,
                                                 self.resource)
        elif isinstance(self.resource, str):
            if os.path.isabs(self.resource) and os.path.exists(self.resource):
                return open(self.resource, "rb")

        raise ValueError
