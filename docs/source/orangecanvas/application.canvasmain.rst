===================================
Canvas Main Window (``canvasmain``)
===================================

.. currentmodule:: orangecanvas.application.canvasmain

.. autoclass:: orangecanvas.application.canvasmain.CanvasMainWindow
   :member-order: bysource
   :show-inheritance:

   .. automethod:: set_widget_registry(widget_registry: WidgetRegistry)

   .. method:: current_document() -> SchemeEditWidget

      Return the current displayed editor (:class:`.SchemeEditWidget`)

   .. automethod:: create_new_window() -> CanvasMainWindow

   .. automethod:: new_workflow_window() -> CanvasMainWindow