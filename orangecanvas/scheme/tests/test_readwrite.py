"""
Test read write
"""
import io
from xml.etree import ElementTree as ET

from ...gui import test
from ...registry import WidgetRegistry, WidgetDescription, CategoryDescription
from ...registry import tests as registry_tests
from ...registry import OutputSignal, InputSignal

from .. import Scheme, SchemeNode, SchemeLink, \
               SchemeArrowAnnotation, SchemeTextAnnotation

from .. import readwrite
from ..readwrite import scheme_to_interm
from ...registry.tests import small_testing_registry


class TestReadWrite(test.QAppTestCase):
    def test_io(self):
        reg = registry_tests.small_testing_registry()

        zero_desc = reg.widget("zero")
        one_desc = reg.widget("one")
        add_desc = reg.widget("add")
        negate = reg.widget("negate")

        scheme = Scheme()
        zero_node = SchemeNode(zero_desc)
        one_node = SchemeNode(one_desc)
        add_node = SchemeNode(add_desc)
        negate_node = SchemeNode(negate)

        scheme.add_node(zero_node)
        scheme.add_node(one_node)
        scheme.add_node(add_node)
        scheme.add_node(negate_node)

        scheme.add_link(SchemeLink(zero_node, "value", add_node, "left"))
        scheme.add_link(SchemeLink(one_node, "value", add_node, "right"))
        scheme.add_link(SchemeLink(add_node, "result", negate_node, "value"))

        scheme.add_annotation(SchemeArrowAnnotation((0, 0), (10, 10)))
        scheme.add_annotation(SchemeTextAnnotation((0, 100, 200, 200), "$$"))

        stream = io.BytesIO()
        readwrite.scheme_to_ows_stream(scheme, stream, pretty=True)

        stream.seek(0)

        scheme_1 = readwrite.scheme_load(Scheme(), stream, reg)

        self.assertTrue(len(scheme.nodes) == len(scheme_1.nodes))
        self.assertTrue(len(scheme.links) == len(scheme_1.links))
        self.assertTrue(len(scheme.annotations) == len(scheme_1.annotations))

        for n1, n2 in zip(scheme.nodes, scheme_1.nodes):
            self.assertEqual(n1.position, n2.position)
            self.assertEqual(n1.title, n2.title)

        for link1, link2 in zip(scheme.links, scheme_1.links):
            self.assertEqual(link1.source_type(), link2.source_type())
            self.assertEqual(link1.sink_type(), link2.sink_type())

            self.assertEqual(link1.source_channel.name,
                             link2.source_channel.name)

            self.assertEqual(link1.sink_channel.name,
                             link2.sink_channel.name)

            self.assertEqual(link1.enabled, link2.enabled)

        for annot1, annot2 in zip(scheme.annotations, scheme_1.annotations):
            self.assertIs(type(annot1), type(annot2))
            if isinstance(annot1, SchemeTextAnnotation):
                self.assertEqual(annot1.text, annot2.text)
                self.assertEqual(annot1.rect, annot2.rect)
            else:
                self.assertEqual(annot1.start_pos, annot2.start_pos)
                self.assertEqual(annot1.end_pos, annot2.end_pos)

    def test_safe_evals(self):
        s = readwrite.string_eval(r"'\x00\xff'")
        self.assertEqual(s, chr(0) + chr(255))

        with self.assertRaises(ValueError):
            readwrite.string_eval("[1, 2]")

        t = readwrite.tuple_eval("(1, 2.0, 'a')")
        self.assertEqual(t, (1, 2.0, 'a'))

        with self.assertRaises(ValueError):
            readwrite.tuple_eval("u'string'")

        with self.assertRaises(ValueError):
            readwrite.tuple_eval("(1, [1, [2, ]])")

        self.assertIs(readwrite.terminal_eval("True"), True)
        self.assertIs(readwrite.terminal_eval("False"), False)
        self.assertIs(readwrite.terminal_eval("None"), None)

        self.assertEqual(readwrite.terminal_eval("42"), 42)
        self.assertEqual(readwrite.terminal_eval("'42'"), '42')
        self.assertEqual(readwrite.terminal_eval(r"b'\xff\x00'"), b'\xff\x00')

    def test_literal_dump(self):
        struct = {1: [{(1, 2): ""}],
                  True: 1.0,
                  None: None}

        s = readwrite.literal_dumps(struct)
        self.assertEqual(readwrite.literal_loads(s), struct)

        with self.assertRaises(ValueError):
            recur = [1]
            recur.append(recur)
            readwrite.literal_dumps(recur)

        with self.assertRaises(TypeError):
            readwrite.literal_dumps(self)

    def test_resolve_replaced(self):
        tree = ET.parse(io.BytesIO(FOOBAR_v20.encode()))
        parsed = readwrite.parse_ows_etree_v_2_0(tree)

        self.assertIsInstance(parsed, readwrite._scheme)
        self.assertEqual(parsed.version, "2.0")
        self.assertTrue(len(parsed.nodes) == 2)
        self.assertTrue(len(parsed.links) == 2)

        qnames = [node.qualified_name for node in parsed.nodes]
        self.assertSetEqual(set(qnames), set(["package.foo", "package.bar"]))

        reg = foo_registry()

        parsed = readwrite.resolve_replaced(parsed, reg)

        qnames = [node.qualified_name for node in parsed.nodes]
        self.assertSetEqual(set(qnames),
                            set(["package.foo", "frob.bar"]))
        projects = [node.project_name for node in parsed.nodes]
        self.assertSetEqual(set(projects), set(["Foo", "Bar"]))

    def test_scheme_to_interm(self):
        workflow = Scheme()
        workflow.load_from(
            io.BytesIO(FOOBAR_v20.encode()),
            registry=foo_registry(with_replaces=False),
        )

        tree = ET.parse(io.BytesIO(FOOBAR_v20.encode()))
        parsed = readwrite.parse_ows_etree_v_2_0(tree)

        interm = scheme_to_interm(workflow)
        self.assertEqual(parsed, interm)


def foo_registry(with_replaces=True):
    reg = WidgetRegistry()
    reg.register_category(CategoryDescription("Quack"))
    reg.register_widget(
        WidgetDescription(
            name="Foo",
            id="foooo",
            qualified_name="package.foo",
            project_name="Foo",
            category="Quack",
            outputs=[
                OutputSignal("foo", "str"),
                OutputSignal("foo1", "int"),
            ]
        )
    )
    reg.register_widget(
        WidgetDescription(
            name="Bar",
            id="barrr",
            qualified_name="frob.bar" if with_replaces else "package.bar",
            project_name="Bar",
            replaces=["package.bar"] if with_replaces else [],
            category="Quack",
            inputs=[
                InputSignal("bar", "str", "bar"),
                InputSignal("bar1", "int", "bar1"),
            ]
        )
    )
    return reg


FOOBAR_v20 = """<?xml version="1.0" ?>
<scheme title="FooBar" description="Foo to the bar" version="2.0">
    <nodes>
        <node id="0" title="Foo" position="1, 2" project_name="Foo"
              qualified_name="package.foo" name="Foo" />
        <node id="1" title="Bar" position="2, 3" project_name="Bar"
              qualified_name="package.bar" name="Bar" />
    </nodes>
    <links>
        <link enabled="true" id="0" sink_channel="bar" sink_node_id="1"
              source_channel="foo" source_node_id="0" />
        <link enabled="false" id="1" sink_channel="bar1" sink_node_id="1"
              source_channel="foo1" source_node_id="0" />
    </links>
    <annotations>
        <text id="0" rect="10, 10, 30, 30" type="text/plain">Hello World</text>
        <arrow id="1" start="30, 30" end="60, 60" fill="red" />
    </annotations>
</scheme>
"""
