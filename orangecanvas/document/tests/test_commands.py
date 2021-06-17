import unittest
from types import SimpleNamespace

from AnyQt.QtWidgets import QUndoStack

from orangecanvas.document import commands
from orangecanvas.registry.tests import small_testing_registry
from orangecanvas.scheme import Scheme, SchemeNode, MetaNode, Link


class TestCommands(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.reg = small_testing_registry()

    @classmethod
    def tearDownClass(cls) -> None:
        del cls.reg
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.stack = QUndoStack()
        self.workflow = Scheme()
        self.root = self.workflow.root()

    def tearDown(self) -> None:
        del self.stack
        del self.workflow
        del self.root
        super().tearDown()

    def test_add_node_command(self):
        node = SchemeNode(self.reg.widget("one"))
        command = commands.AddNodeCommand(self.workflow, node, self.root)
        self.stack.push(command)
        self.assertSequenceEqual(self.root.nodes(), [node])
        self.stack.undo()
        self.assertSequenceEqual(self.root.nodes(), [])

    def test_remove_node_command(self):
        node = SchemeNode(self.reg.widget("one"))
        self.root.add_node(node)
        command = commands.RemoveNodeCommand(self.workflow, node, self.root)
        self.stack.push(command)
        self.assertSequenceEqual(self.root.nodes(), [])
        self.stack.undo()
        self.assertSequenceEqual(self.root.nodes(), [node])

    @classmethod
    def _setup_workflow_with_macro(cls, workflow: Scheme):
        root = workflow.root()
        one1 = SchemeNode(cls.reg.widget("one"))
        one2 = SchemeNode(cls.reg.widget("one"))
        add = SchemeNode(cls.reg.widget("add"))
        neg = SchemeNode(cls.reg.widget("negate"))
        meta = MetaNode()
        i1 = meta.create_input_node(add.input_channels()[0])
        o1 = meta.create_output_node(add.output_channels()[0])
        meta.add_node(add)
        meta.add_node(one2)
        meta.add_link(
            Link(i1, i1.output_channels()[0], add, add.input_channels()[0]))
        meta.add_link(
            Link(one2, one2.output_channels()[0], add, add.input_channels()[1]))
        meta.add_link(
            Link(add, add.output_channels()[0], o1, o1.input_channels()[0]))

        root.add_node(one1)
        root.add_node(meta)
        root.add_node(neg)
        l1 = Link(one1, one1.output_channels()[0], meta, meta.input_channels()[0])
        root.add_link(l1)
        l2 = Link(meta, meta.output_channels()[0], neg, neg.input_channels()[0])
        root.add_link(l2)
        return SimpleNamespace(
            root=root, one1=one1, one2=one2, add=add, neg=neg, meta=meta,
            i1=i1, o1=o1, l1=l1, l2=l2)

    def test_remove_macro_node(self):
        ns = self._setup_workflow_with_macro(self.workflow)
        command = commands.RemoveNodeCommand(self.workflow, ns.meta, ns.root)
        self.stack.push(command)
        self.assertSequenceEqual(self.root.nodes(), [ns.one1, ns.neg])
        self.assertSequenceEqual(self.root.links(), [])
        self.assertIs(ns.meta.parent_node(), None)
        self.stack.undo()
        self.assertIs(ns.meta.parent_node(), self.root)
        self.assertSequenceEqual(self.root.nodes(), [ns.one1, ns.meta, ns.neg])
        self.assertSequenceEqual(self.root.links(), [ns.l1, ns.l2])

    def test_remove_input_node(self):
        ns = self._setup_workflow_with_macro(self.workflow)
        command = commands.RemoveNodeCommand(self.workflow, ns.i1, ns.meta)
        self.stack.push(command)
        self.assertSequenceEqual(self.root.links(), [ns.l2])
        self.assertSequenceEqual(ns.meta.input_channels(), [])
        self.stack.undo()
        self.assertSequenceEqual(self.root.links(), [ns.l1, ns.l2])
        self.assertSequenceEqual(ns.meta.input_channels(), [ns.i1.input_channels()[0]])

    def test_remove_output_node(self):
        ns = self._setup_workflow_with_macro(self.workflow)
        command = commands.RemoveNodeCommand(self.workflow, ns.o1, ns.meta)
        self.stack.push(command)
        self.assertSequenceEqual(self.root.links(), [ns.l1])
        self.assertSequenceEqual(ns.meta.output_channels(), [])
        self.stack.undo()
        self.assertSequenceEqual(self.root.links(), [ns.l1, ns.l2])
        self.assertSequenceEqual(ns.meta.output_channels(), [ns.o1.output_channels()[0]])
