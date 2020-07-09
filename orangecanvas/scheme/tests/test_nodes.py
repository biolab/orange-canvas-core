"""
"""
from AnyQt.QtTest import QSignalSpy

from ...gui import test
from ...registry.tests import small_testing_registry
from ...registry import InputSignal, OutputSignal

from .. import SchemeNode


class TestScheme(test.QAppTestCase):
    def test_node(self):
        """Test SchemeNode.
        """
        reg = small_testing_registry()
        one_desc = reg.widget("one")

        node = SchemeNode(one_desc)

        inputs = node.input_channels()
        self.assertSequenceEqual(inputs, one_desc.inputs)
        for ch in inputs:
            channel = node.input_channel(ch.name)
            self.assertIsInstance(channel, InputSignal)
            self.assertTrue(channel in inputs)
        self.assertRaises(ValueError, node.input_channel, "%%&&&$$()[()[")

        outputs = node.output_channels()
        self.assertSequenceEqual(outputs, one_desc.outputs)
        for ch in outputs:
            channel = node.output_channel(ch.name)
            self.assertIsInstance(channel, OutputSignal)
            self.assertTrue(channel in outputs)
        self.assertRaises(ValueError, node.output_channel, "%%&&&$$()[()[")

    def test_channels_by_name_or_id(self):
        reg = small_testing_registry()

        zero_desc = reg.widget("zero")
        node = SchemeNode(zero_desc)
        self.assertIs(node.output_channel("value"), zero_desc.outputs[0])
        self.assertIs(node.output_channel("val"), zero_desc.outputs[0])

        add_desc = reg.widget("add")
        node = SchemeNode(add_desc)
        self.assertIs(node.input_channel("left"), add_desc.inputs[0])
        self.assertIs(node.input_channel("right"), add_desc.inputs[1])
        self.assertIs(node.input_channel("droite"), add_desc.inputs[1])
        self.assertRaises(ValueError, node.input_channel, "gauche")

    def test_insert_remove_io(self):
        reg = small_testing_registry()
        node = SchemeNode(reg.widget("add"))
        inserted = QSignalSpy(node.input_channel_inserted)
        removed = QSignalSpy(node.input_channel_removed)
        input = InputSignal("input", "int", "")

        with self.assertRaises(IndexError):
            node.insert_input_channel(0, input)
        node.insert_input_channel(2, input)
        self.assertSequenceEqual(list(inserted), [[2, input]])
        self.assertSequenceEqual(
            node.input_channels(), [*node.description.inputs, input]
        )

        with self.assertRaises(IndexError):
            node.remove_input_channel(0)

        node.remove_input_channel(2)
        self.assertSequenceEqual(list(removed), [[2, input]])
        self.assertSequenceEqual(node.input_channels(), node.description.inputs)

        inserted = QSignalSpy(node.output_channel_inserted)
        removed = QSignalSpy(node.output_channel_removed)

        output = OutputSignal("a", "int")
        with self.assertRaises(IndexError):
            node.insert_output_channel(0, output)

        node.insert_output_channel(1, output)
        self.assertSequenceEqual(list(inserted), [[1, output]])
        self.assertSequenceEqual(
            node.output_channels(), [*node.description.outputs, output]
        )
        with self.assertRaises(IndexError):
            node.remove_output_channel(0)

        node.remove_output_channel(1)
        self.assertSequenceEqual(list(removed), [[1, output]])
