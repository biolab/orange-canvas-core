.. _Overview:

Overview
########

.. currentmodule:: orangecanvas

Orange Canvas application is build around the a workflow model (scheme),
which is implemented in the :mod:`~orangecanvas.scheme` package. Briefly
speaking a workflow is a simple graph structure(a Directed Acyclic
Graph - DAG). The nodes in this graph represent some action/task to be
computed. A node in this graph has a set of inputs and outputs on which it
receives and sends objects.

The set of available node types for a workflow are kept in a
(:class:`~orangecanvas.registry.WidgetRegistry`).
:class:`~orangecanvas.registry.WidgetDiscovery` can be used (but not
required) to populate the registry.


Common reusable gui elements used for building the user interface
reside in the :mod:`~orangecanvas.gui` package.


Workflow Model
**************

The workflow model is implemented by :class:`~scheme.scheme.Scheme`.
It is composed by a set of node (:class:`~scheme.node.SchemeNode`)
instances and links (:class:`~scheme.link.SchemeLink`) between them.
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

The runtime execution (propagation of node's outputs to dependent
node inputs) is handled by the signal manager.

* :class:`~scheme.signalmanager.SignalManager`


Workflow Node GUI
-----------------

A WidgetManager is responsible for managing GUI corresponsing to individual
nodes in the workflow.

* :class:`~scheme.widgetmanager.WidgetManager`

Workflow View
*************

* The workflow view (:class:`~canvas.scene.CanvasScene`)
* The workflow editor (:class:`~document.schemeedit.SchemeEditWidget`)


Application
***********

Joining everything together, the final application (main window, ...)
is implemented in :mod:`orangecanvas.application`.
