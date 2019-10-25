import unittest

from AnyQt.QtWidgets import QApplication
from AnyQt.QtTest import QSignalSpy

from orangecanvas.scheme import Scheme, SchemeNode, SchemeLink
from orangecanvas.scheme import signalmanager
from orangecanvas.scheme.signalmanager import (
    SignalManager, Signal,  compress_signals
)
from orangecanvas.registry import tests as registry_tests


class TestingSignalManager(SignalManager):
    def is_blocking(self, node):
        return bool(node.property("-blocking"))

    def send_to_node(self, node, signals):
        for sig in signals:
            name = sig.link.sink_channel.name
            node.setProperty("-input-" + name, sig.value)

        for out in node.description.outputs:
            self.send(node, out, "hello", None)


class TestSignalManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        cls.app = app

    @classmethod
    def tearDownClass(cls):
        del cls.app

    def setUp(self):
        reg = registry_tests.small_testing_registry()
        scheme = Scheme()
        zero = scheme.new_node(reg.widget("zero"))
        one = scheme.new_node(reg.widget("one"))
        add = scheme.new_node(reg.widget("add"))
        scheme.new_link(zero, "value", add, "left")
        scheme.new_link(one, "value", add, "right")
        self.reg = reg
        self.scheme = scheme

    def test(self):
        workflow = self.scheme
        sm = TestingSignalManager()
        sm.set_workflow(workflow)
        sm.set_workflow(workflow)
        sm.set_workflow(None)
        sm.set_workflow(workflow)
        sm.start()

        self.assertFalse(sm.has_pending())

        sm.stop()
        sm.pause()
        sm.resume()
        n0, n1, n3 = workflow.nodes

        sm.send(n0, n0.description.outputs[0], 'hello', None)
        sm.send(n1, n1.description.outputs[0], 'hello', None)
        spy = QSignalSpy(sm.processingFinished[SchemeNode])
        self.assertTrue(spy.wait())
        self.assertSequenceEqual(list(spy), [[n3]])
        self.assertEqual(n3.property("-input-left"), 'hello')
        self.assertEqual(n3.property("-input-right"), 'hello')

        self.assertFalse(sm.has_pending())
        workflow.remove_link(workflow.links[0])
        self.assertTrue(sm.has_pending())

        spy = QSignalSpy(sm.processingFinished[SchemeNode])
        self.assertTrue(spy.wait())

        self.assertEqual(n3.property("-input-left"), None)
        self.assertEqual(n3.property("-input-right"), 'hello')

    def test_invalidated_flags(self):
        workflow = self.scheme
        sm = TestingSignalManager()
        sm.set_workflow(workflow)
        sm.start()

        n0, n1, n2 = workflow.nodes[:3]
        l0, l1 = workflow.links[:2]

        self.assertFalse(l0.runtime_state() & SchemeLink.Invalidated)
        sm.send(n0, n0.description.outputs[0], 'hello', None)
        self.assertFalse(l0.runtime_state() & SchemeLink.Invalidated)
        self.assertIn(n2, sm.node_update_front())

        sm.invalidate(n0, n0.description.outputs[0])
        self.assertTrue(l0.runtime_state() & SchemeLink.Invalidated)
        self.assertTrue(sm.has_invalidated_outputs(n0))
        self.assertTrue(sm.has_invalidated_inputs(n2))
        self.assertNotIn(n2, sm.node_update_front())

        sm.send(n0, n0.description.outputs[0], 'hello', None)
        self.assertFalse(l0.runtime_state() & SchemeLink.Invalidated)
        self.assertFalse(sm.has_invalidated_outputs(n0))
        self.assertFalse(sm.has_invalidated_inputs(n2))
        self.assertIn(n2, sm.node_update_front())

        sm.invalidate(n1, n1.description.outputs[0])
        n3 = workflow.new_node(self.reg.widget('add'))
        l2 = workflow.new_link(
            n1, n1.output_channel('value'), n3, n3.input_channel('left')
        )

        self.assertTrue(l2.test_runtime_state(SchemeLink.Invalidated))
        self.assertTrue(sm.has_invalidated_inputs(n3))
        self.assertNotIn(n3, sm.node_update_front())

        workflow.remove_link(l2)
        self.assertFalse(sm.has_invalidated_inputs(n3))
        self.assertNotIn(n3, sm.node_update_front())

        # invalidated must not propagate via disabled links
        self.assertNotIn(n2, sm.node_update_front())
        l1.set_enabled(False)
        self.assertIn(n2, sm.node_update_front())
        self.assertFalse(sm.has_invalidated_inputs(n2))
        l1.set_enabled(True)
        self.assertNotIn(n2, sm.node_update_front())
        self.assertTrue(sm.has_invalidated_inputs(n2))

    def test_pending_flags(self):
        workflow = self.scheme
        sm = TestingSignalManager()
        sm.set_workflow(workflow)
        sm.start()
        n0, n1, n3 = workflow.nodes[:3]
        l0, l1 = workflow.links[:2]

        self.assertFalse(n3.test_state_flags(SchemeNode.Pending))
        self.assertFalse(l0.runtime_state() & SchemeLink.Pending)
        sm.send(n0, n0.description.outputs[0], 'hello', None)
        self.assertTrue(n3.test_state_flags(SchemeNode.Pending))
        self.assertTrue(l0.runtime_state() & SchemeLink.Pending)

        spy = QSignalSpy(sm.processingFinished)
        assert spy.wait()

        self.assertFalse(n3.test_state_flags(SchemeNode.Pending))
        self.assertFalse(l0.runtime_state() & SchemeLink.Pending)

    def test_compress_signals(self):
        workflow = self.scheme
        link = workflow.links[0]
        self.assertSequenceEqual(compress_signals([]), [])
        signals_in = [
            Signal(link, 1, None),
            Signal(link, 3, None),
            Signal(link, 2, None),
        ]
        self.assertSequenceEqual(
            compress_signals(signals_in),
            signals_in[-1:]
        )
        signals_in = [
            Signal(link, None, None),
            Signal(link, 3, None),
            Signal(link, 2, None),
        ]
        self.assertSequenceEqual(
            compress_signals(signals_in),
            [signals_in[0], signals_in[-1]]
        )
        signals_in = [
            Signal(link, None, 1),
            Signal(link, 3, 1),
            Signal(link, 2, 2),
        ]
        self.assertSequenceEqual(
            compress_signals(signals_in),
            signals_in,
        )
        signals_in = [
            Signal(link, 1, 1),
            Signal(link, None, 1),
            Signal(link, 2, 2),
        ]
        self.assertSequenceEqual(
            compress_signals(signals_in),
            signals_in[1:],
        )


class TestSCC(unittest.TestCase):
    def test_scc(self):
        E1 = {}
        scc = signalmanager.strongly_connected_components(E1, E1.__getitem__)
        self.assertEqual(scc, [])

        E2 = {1: []}
        scc = signalmanager.strongly_connected_components(E2, E2.__getitem__)
        self.assertEqual(scc, [[1]])

        T1 = {1: [2, 3], 2: [4, 5], 3: [6, 7], 4: [], 5: [], 6: [], 7: []}
        scc = signalmanager.strongly_connected_components(T1, T1.__getitem__)
        self.assertEqual(scc, [[4], [5], [2], [6], [7], [3], [1]])

        C1 = {1: [2], 2: [3], 3: [1]}
        scc = signalmanager.strongly_connected_components(C1, C1.__getitem__)
        self.assertEqual(scc, [[1, 2, 3]])

        G1 = {1: [2, 3], 2: [3, 5], 3: [], 5: [2]}
        scc = signalmanager.strongly_connected_components(G1, G1.__getitem__)
        self.assertEqual(scc, [[3], [2, 5], [1]])

        DAG1 = {1: [2, 3], 2: [3], 3: [4], 4: []}
        scc = signalmanager.strongly_connected_components(
            DAG1, DAG1.__getitem__)
        self.assertEqual(scc, [[4], [3], [2], [1]])

        G2 = {1: [2], 2: [1, 5], 3: [4], 4: [3, 5], 5: [6],
              6: [7], 7: [8], 8: [6, 9], 9: []}
        scc = signalmanager.strongly_connected_components(G2, G2.__getitem__)
        self.assertEqual(scc, [[9], [6, 7, 8], [5], [1, 2], [3, 4]])

        G3 = {1: [2], 2: [3], 3: [1],
              4: [5, 3], 5: [4, 6],
              6: [3, 7], 7: [6],
              8: [8]}
        scc = signalmanager.strongly_connected_components(G3, G3.__getitem__)
        self.assertEqual(scc, [[1, 2, 3], [6, 7], [4, 5], [8]])
