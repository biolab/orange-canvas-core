Overview
########

.. currentmodule:: orangecanvas

Orange Canvas application is build around the a workflow model (scheme),
which is implemented in the :mod:`~orangecanvas.scheme` package. Briefly
speaking a workflow is a simple graph structure (most commonly a
Directed Acyclic Graph - DAG). The nodes in this graph represent some
action/task to be computed. A node (also commonly referred to as a
*widget*) has a set of inputs and outputs on which it receives and
sends objects.

The set of available node types for a workflow are kept in a
(:class:`~orangecanvas.registry.WidgetRegistry`).
:class:`~orangecanvas.registry.WidgetDiscovery` can be used (but not
required) to populate the registry.

..
    Common reusable gui elements used for building the user interface
    reside in th :mod:`~orangecanvas.gui` package.


Workflow Model
**************

The workflow model is implemented by :class:`~scheme.Scheme`.
It is composed by a set of node (:class:`~scheme.SchemeNode`)
instances and links (:class:`~scheme.SchemeLink`) between them.
Every node has a corresponding :class:`~registry.WidgetDescription`
defining its inputs and outputs (restricting the node's connectivity).

In addition, it can also contain workflow annotations. These are only
used when displaying the workflow in a GUI.

Widget Description
------------------

* :class:`~registry.WidgetDescription`
* :class:`~registry.CategoryDescription`


Workflow Execution
------------------

* :class:`~scheme.signalmanager.SignalManager`

Workflow View
*************

* The workflow view (:class:`~canvas.scene.CanvasScene`)
* The workflow editor (:class:`~document.schemeedit.SchemeEditWidget`)
