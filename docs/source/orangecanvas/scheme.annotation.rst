.. schemeannotation:

====================================
Scheme Annotations (``annotations``)
====================================

.. automodule:: orangecanvas.scheme.annotations


.. autoclass:: Annotation
   :members:
   :member-order: bysource
   :show-inheritance:

   .. autoattribute:: geometry_changed()

      Signal emitted when the geometry of the annotation changes


.. autoclass:: ArrowAnnotation
   :members:
   :member-order: bysource
   :show-inheritance:


.. autoclass:: TextAnnotation
   :members:
   :member-order: bysource
   :show-inheritance:

   .. autoattribute:: text_changed(str)

      Signal emitted when the annotation text changes.
