.. scheme:

===================
Scheme (``scheme``)
===================

.. automodule:: orangecanvas.scheme.scheme

.. autoclass:: Scheme
   :members:
   :exclude-members: runtime_env_changed
   :member-order: bysource
   :show-inheritance:

   .. autoattribute:: title_changed(title)

      Signal emitted when the title of scheme changes.

   .. autoattribute:: description_changed(description)

      Signal emitted when the description of scheme changes.

   .. autoattribute:: node_added(node)

      Signal emitted when a `node` is added to the scheme.

   .. autoattribute:: node_removed(node)

      Signal emitted when a `node` is removed from the scheme.

   .. autoattribute:: link_added(link)

      Signal emitted when a `link` is added to the scheme.

   .. autoattribute:: link_removed(link)

      Signal emitted when a `link` is removed from the scheme.

   .. autoattribute:: annotation_added(annotation)

      Signal emitted when a `annotation` is added to the scheme.

   .. autoattribute:: annotation_removed(annotation)

      Signal emitted when a `annotation` is removed from the scheme.

   .. autoattribute:: runtime_env_changed(key: str, newvalue: Optional[str], oldvalue: Optional[str])


.. autoclass:: SchemeCycleError
   :show-inheritance:


.. autoclass:: IncompatibleChannelTypeError
   :show-inheritance:


.. autoclass:: SinkChannelError
   :show-inheritance:


.. autoclass:: DuplicatedLinkError
   :show-inheritance:
