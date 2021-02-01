.. scheme-node:

===============
Node (``node``)
===============

.. automodule:: orangecanvas.scheme.node

.. autoclass:: Node
   :members:
   :exclude-members:
      title_changed,
      position_changed,
      progress_changed,
      processing_state_changed,
      input_channel_inserted,
      input_channel_removed,
      output_channel_inserted,
      output_channel_removed
   :member-order: bysource
   :show-inheritance:

   .. autoattribute:: title_changed(title)

   .. autoattribute:: position_changed((x, y))

   .. autoattribute:: progress_changed(progress)

   .. autoattribute:: processing_state_changed(state)

   .. autoattribute:: input_channel_inserted(index, signal)

   .. autoattribute:: input_channel_removed(signal)

   .. autoattribute:: output_channel_inserted(index, signal)

   .. autoattribute:: output_channel_removed(signal)


.. autoclass:: SchemeNode
   :members:
   :member-order: bysource
   :show-inheritance:
