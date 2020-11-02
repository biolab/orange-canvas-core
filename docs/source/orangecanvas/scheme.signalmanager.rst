.. signalmanager:

.. automodule:: orangecanvas.scheme.signalmanager

.. autoclass:: SignalManager
   :members:
   :member-order: bysource
   :exclude-members:
      stateChanged,
      updatesPending,
      processingStarted,
      processingFinished,
      runtimeStateChanged
   :show-inheritance:

   .. autoattribute:: stateChanged(State)

   .. autoattribute:: updatesPending()

   .. autoattribute:: processingStarted(SchemeNode)

   .. autoattribute:: processingFinished(SchemeNode)

   .. autoattribute:: runtimeStateChanged(RuntimeState)

.. autoclass:: Signal
   :members:
