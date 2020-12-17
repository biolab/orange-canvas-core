.. workflow-events:

============================
Workflow Events (``events``)
============================

.. py:currentmodule:: orangecanvas.scheme.events


.. autoclass:: orangecanvas.scheme.events.WorkflowEvent
   :show-inheritance:

   .. autoattribute:: NodeAdded
      :annotation: = QEvent.Type(...)
   .. autoattribute:: NodeRemoved
      :annotation: = QEvent.Type(...)
   .. autoattribute:: LinkAdded
      :annotation: = QEvent.Type(...)
   .. autoattribute:: LinkRemoved
      :annotation: = QEvent.Type(...)
   .. autoattribute:: InputLinkAdded
      :annotation: = QEvent.Type(...)
   .. autoattribute:: OutputLinkAdded
      :annotation: = QEvent.Type(...)
   .. autoattribute:: InputLinkRemoved
      :annotation: = QEvent.Type(...)
   .. autoattribute:: OutputLinkRemoved
      :annotation: = QEvent.Type(...)
   .. autoattribute:: NodeStateChange
      :annotation: = QEvent.Type(...)
   .. autoattribute:: LinkStateChange
      :annotation: = QEvent.Type(...)
   .. autoattribute:: InputLinkStateChange
      :annotation: = QEvent.Type(...)
   .. autoattribute:: OutputLinkStateChange
      :annotation: = QEvent.Type(...)
   .. autoattribute:: NodeActivateRequest
      :annotation: = QEvent.Type(...)
   .. autoattribute:: WorkflowEnvironmentChange
      :annotation: = QEvent.Type(...)
   .. autoattribute:: AnnotationAdded
      :annotation: = QEvent.Type(...)
   .. autoattribute:: AnnotationRemoved
      :annotation: = QEvent.Type(...)
   .. autoattribute:: AnnotationChange
      :annotation: = QEvent.Type(...)
   .. autoattribute:: ActivateParentRequest
      :annotation: = QEvent.Type(...)


.. autoclass:: orangecanvas.scheme.events.NodeEvent
   :show-inheritance:

   .. automethod:: node() -> SchemeNode
   .. automethod:: pos() -> int


.. autoclass:: orangecanvas.scheme.events.LinkEvent
   :show-inheritance:

   .. automethod:: link() -> SchemeLink
   .. automethod:: pos() -> int


.. autoclass:: orangecanvas.scheme.events.AnnotationEvent
   :show-inheritance:

   .. automethod:: annotation() -> BaseSchemeAnnotation
   .. automethod:: pos() -> int


.. autoclass:: orangecanvas.scheme.events.WorkflowEnvChanged
   :show-inheritance:

   .. automethod:: name() -> str
   .. automethod:: oldValue() -> Any
   .. automethod:: newValue() -> Any
