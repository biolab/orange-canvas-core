==================================
Welcome Dialog (``welcomedialog``)
==================================

.. currentmodule:: orangecanvas.application.welcomedialog

.. autoclass:: orangecanvas.application.welcomedialog.WelcomeDialog
   :member-order: bysource
   :show-inheritance:

   .. method:: triggered(QAction)

      Signal emitted when an action is triggered by the user

   .. automethod:: setShowAtStartup(state: bool)

   .. automethod:: showAtStartup() -> bool

   .. automethod:: setFeedbackUrl(url: str)

   .. automethod:: addRow(actions: List[QAction])

   .. automethod:: buttonAt(i: int, j: int) -> QAbstractButton