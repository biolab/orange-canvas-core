import unittest

from AnyQt.QtTest import QSignalSpy

from orangecanvas.scheme import Scheme, SchemeNode, SchemeLink
from orangecanvas.scheme import signalmanager
from orangecanvas.scheme.signalmanager import (
    SignalManager, Signal, compress_signals, compress_single
)
from orangecanvas.registry import tests as registry_tests
from orangecanvas.gui.test import QCoreAppTestCase


class TestingSignalManager(SignalManager):
    def is_blocking(self, node):
        return bool(node.property("-blocking"))

    def send_to_node(self, node, signals):
        for sig in signals:
            name = sig.link.sink_channel.name
            node.setProperty("-input-" + name, sig.value)

        for out in node.description.outputs:
            self.send(node, out, "hello")


class TestSignalManager(QCoreAppTestCase):
    def setUp(self):
        super().setUp()
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

        sm.send(n0, n0.description.outputs[0], 'hello')
        sm.send(n1, n1.description.outputs[0], 'hello')
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

    def test_add_link_disabled(self):
        workflow = self.scheme
        sm = TestingSignalManager()
        sm.set_workflow(workflow)
        sm.start()
        n0, n1, n2 = workflow.nodes
        l0, l1 = workflow.links
        workflow.remove_link(l0)
        sm.send(n0, n0.description.outputs[0], 1)
        sm.send(n1, n1.description.outputs[0], 2)
        sm.process_queued()

        self.assertFalse(sm.has_pending())
        l0.set_enabled(False)
        workflow.insert_link(0, l0)
        self.assertSequenceEqual(
            sm.pending_input_signals(n2), [Signal.New(l0, None, None, 0)]
        )
        l0.set_enabled(True)
        self.assertSequenceEqual(
            sm.pending_input_signals(n2),
            [
                Signal.New(l0, None, None, 0),
                Signal.Update(l0, 1, None, 0),
            ]
        )

    def test_invalidated_flags(self):
        workflow = self.scheme
        sm = TestingSignalManager()
        sm.set_workflow(workflow)
        sm.start()

        n0, n1, n2 = workflow.nodes[:3]
        l0, l1 = workflow.links[:2]

        self.assertFalse(l0.runtime_state() & SchemeLink.Invalidated)
        sm.send(n0, n0.description.outputs[0], 'hello')
        self.assertFalse(l0.runtime_state() & SchemeLink.Invalidated)
        self.assertIn(n2, sm.node_update_front())

        sm.invalidate(n0, n0.description.outputs[0])
        self.assertTrue(l0.runtime_state() & SchemeLink.Invalidated)
        self.assertTrue(sm.has_invalidated_outputs(n0))
        self.assertTrue(sm.has_invalidated_inputs(n2))
        self.assertNotIn(n2, sm.node_update_front())

        sm.send(n0, n0.description.outputs[0], 'hello')
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
        sm.send(n0, n0.description.outputs[0], 'hello')
        self.assertTrue(n3.test_state_flags(SchemeNode.Pending))
        self.assertTrue(l0.runtime_state() & SchemeLink.Pending)

        spy = QSignalSpy(sm.processingFinished)
        assert spy.wait()

        self.assertFalse(n3.test_state_flags(SchemeNode.Pending))
        self.assertFalse(l0.runtime_state() & SchemeLink.Pending)

    def test_ready_flags(self):
        workflow = self.scheme
        sm = TestingSignalManager()
        sm.set_workflow(workflow)
        sm.start()

        n0, n1, n3 = workflow.nodes[:3]
        l0, l1 = workflow.links[:2]
        sm.send(n0, n0.output_channel("value"), 'hello')
        sm.send(n1, n1.output_channel("value"), 'hello')
        self.assertIn(n3, sm.node_update_front())
        n3.set_state_flags(SchemeNode.NotReady, True)
        spy = QSignalSpy(sm.processingStarted[SchemeNode])
        sm.process_next()
        self.assertNotIn([n3], list(spy))
        n3.set_state_flags(SchemeNode.NotReady, False)
        assert spy.wait()
        self.assertIn([n3], list(spy))

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
        signals_in = [
            Signal(link, None, 1),
            Signal(link, None, 1),
        ]
        self.assertSequenceEqual(
            compress_signals(signals_in),
            signals_in[1:],
        )

    def test_compress_signals_single(self):
        New, Update, Close = Signal.New, Signal.Update, Signal.Close
        workflow = self.scheme
        link = workflow.links[0]
        self.assertSequenceEqual(
            compress_single([]), []
        )
        signals = [Update(link, None, 1)]
        self.assertSequenceEqual(
            compress_single(signals), signals
        )
        signals = [Update(link, None, 1), Update(link, 1, 1)]
        self.assertSequenceEqual(
            compress_single(signals), signals
        )
        signals = [Update(link, 1, 1), Update(link, None, 1)]
        self.assertSequenceEqual(
            compress_single(signals), [signals[-1]]
        )
        signals = [
            Update(link, None, 1),
            Update(link, 1, 1),
            Update(link, None, 1),
        ]
        self.assertSequenceEqual(
            compress_single(signals),
            [signals[-1]]
        )
        signals = [
            Update(link, None, 1),
            Update(link, 1, 1),
            Update(link, 2, 1),
        ]
        self.assertSequenceEqual(
            compress_single(signals),
            [signals[0], signals[-1]]
        )
        signals = [New(link, None, 1), Close(link, None, 1)]
        self.assertSequenceEqual(
            compress_single(signals), signals,
        )
        signals = [
            New(link, 1, 1),
            Update(link, 2, 1),
            Close(link, None, 1)
        ]
        self.assertSequenceEqual(
            compress_single(signals), [signals[0], signals[-1]]
        )
        signals = [
            New(link, 1, 1),
            Update(link, 1, 1),
            Close(link, None, 1),
            New(link, 1, 1)
        ]
        self.assertSequenceEqual(
            compress_single(signals),
            [signals[0], *signals[2:]]
        )
        signals = [
            Update(link, 1, 1),
            Update(link, 2, 1),
            Close(link, None, 1)
        ]
        self.assertSequenceEqual(
            compress_single(signals), [signals[-1]]
        )
        signals = [
            Update(link, 1, 1),
            Update(link, None, 1),
            Update(link, 2, 1),
            Close(link, None, 1)
        ]
        self.assertSequenceEqual(
            compress_single(signals), [signals[-1]],
        )
        signals = [
            Update(link, 1, 1),
            Update(link, 2, 1),
            Close(link, None, 1),
        ]
        self.assertSequenceEqual(
            compress_single(signals), [signals[-1]]
        )
        signals = [
            Update(link, 1, 1),
            Update(link, 2, 1),
            Close(link, None, 1),
            New(link, None, 1),
        ]
        self.assertSequenceEqual(
            compress_single(signals), signals[-2:]
        )

    def test_compress_signals_typed(self):
        l1, l2 = self.scheme.links[0], self.scheme.links[1]
        New, Update, Close = Signal.New, Signal.Update, Signal.Close
        signals = [
            New(l1, 1, index=0),
            Update(l1, 2, index=0),
            New(l2, "a", index=0),
            Update(l2, 2, index=0),
            Close(l1, None, index=1),
            New(l1, None, index=1),
            Update(l2, "b", index=0)
        ]
        # must preserve relative order of New/Close
        self.assertSequenceEqual(
            compress_signals(signals),
            [
                New(l1, 1, index=0),
                New(l2, "a", index=0),
                Close(l1, None, index=1),
                New(l1, None, index=1),
                Update(l2, "b", index=0)
            ],
        )
        signals = [
            Update(l1, 2, index=0),
            New(l2, "a", index=0),
            Update(l2, 2, index=0),
            Close(l1, None, index=1),
        ]
        self.assertSequenceEqual(
            compress_signals(signals),
            [
                New(l2, "a", index=0),
                Update(l2, 2, index=0),
                Close(l1, None, index=1),
            ],
        )
