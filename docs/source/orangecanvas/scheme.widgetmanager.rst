.. widgetmanager:

=================================
WidgetManager (``widgetmanager``)
=================================

.. automodule:: orangecanvas.scheme.widgetmanager


.. autoclass:: WidgetManager
   :members:
   :exclude-members:
      widget_for_node_added, widget_for_node_removed
   :member-order: bysource
   :show-inheritance:

   .. autoattribute:: widget_for_node_added(SchemeNode, QWidget)

      Signal emitted when a QWidget was created and added by the manager.

   .. autoattribute:: widget_for_node_removed(SchemeNode, QWidget)

      Signal emitted when a QWidget was removed and will be deleted.
