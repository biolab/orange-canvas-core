"""
Test read write
"""
import io
from xml.etree import ElementTree as ET

from ...gui import test
from ...registry import WidgetRegistry, WidgetDescription, CategoryDescription, \
    InputSignal, OutputSignal
from ...registry import tests as registry_tests

from .. import Scheme, SchemeNode, SchemeLink, \
    SchemeArrowAnnotation, SchemeTextAnnotation, MetaNode

from .. import readwrite


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

        self.assertEqual(len(scheme.all_nodes()), len(scheme_1.all_nodes()))
        self.assertEqual(len(scheme.all_links()), len(scheme_1.all_links()))
        self.assertEqual(len(scheme.all_annotations()), len(scheme_1.all_annotations()))

        for n1, n2 in zip(scheme.all_nodes(), scheme_1.all_nodes()):
            self.assertEqual(n1.position, n2.position)
            self.assertEqual(n1.title, n2.title)

        for link1, link2 in zip(scheme.all_links(), scheme_1.all_links()):
            self.assertEqual(link1.source_types(), link2.source_types())
            self.assertEqual(link1.sink_types(), link2.sink_types())

            self.assertEqual(link1.source_channel.name,
                             link2.source_channel.name)

            self.assertEqual(link1.sink_channel.name,
                             link2.sink_channel.name)

            self.assertEqual(link1.enabled, link2.enabled)

        for annot1, annot2 in zip(scheme.all_annotations(), scheme_1.all_annotations()):
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
            readwrite.string_eval("3")

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
        self.assertEqual(readwrite.terminal_eval("42."), 42.)
        self.assertEqual(readwrite.terminal_eval("'42'"), '42')
        self.assertEqual(readwrite.terminal_eval(r"b'\xff\x00'"), b'\xff\x00')
        with self.assertRaises(ValueError):
            readwrite.terminal_eval("...")
        with self.assertRaises(ValueError):
            readwrite.terminal_eval("{}")

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

        with self.assertRaises(TypeError):
            readwrite.literal_dumps(float("nan"))

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

    def test_dynamic_io_channels(self):
        reg = foo_registry()
        scheme = Scheme()
        node = SchemeNode(reg.widget("frob.bar"))
        scheme.add_node(node)
        node.add_input_channel(InputSignal("a", "int", ""))
        node.add_input_channel(InputSignal("b", "str", ""))

        node.add_output_channel(OutputSignal("a", "int",))
        node.add_output_channel(OutputSignal("b", "str"))

        stream = io.BytesIO()
        readwrite.scheme_to_ows_stream(scheme, stream, )
        stream.seek(0)
        scheme_1 = Scheme()
        readwrite.scheme_load(scheme_1, stream, reg)
        node_1 = scheme_1.root().nodes()[0]
        self.assertEqual(node_1.input_channels()[-1].name, "b")
        self.assertEqual(node_1.output_channels()[-1].name, "b")

    def test_macro(self):
        tree = ET.parse(io.BytesIO(FOOBAR_v30.encode()))
        root = readwrite.parse_ows_etree_v_3_0(tree)
        self.assertEqual(len(root.nodes), 3)
        self.assertEqual(len(root.links), 2)
        macro = root.nodes[2]
        self.assertIsInstance(macro, readwrite._macro_node)
        self.assertEqual(len(macro.nodes), 3)
        self.assertEqual(len(macro.links), 2)
        self.assertEqual(len(macro.annotations), 1)

        workflow = Scheme()
        reg = foo_registry()
        workflow.load_from(io.BytesIO(FOOBAR_v30.encode()), registry=reg)
        root = workflow.root()
        macro = root.nodes()[2]
        self.assertIsInstance(macro, MetaNode)
        self.assertEqual(len(macro.nodes()), 3)
        self.assertEqual(len(macro.links()), 2)
        self.assertEqual(len(macro.annotations()), 1)

        stream = io.BytesIO()
        workflow.save_to(stream, )
        workflow.clear()
        stream.seek(0)
        workflow.load_from(stream, registry=reg)

        root = workflow.root()
        macro = root.nodes()[2]
        self.assertIsInstance(macro, MetaNode)
        self.assertEqual(len(macro.nodes()), 3)
        self.assertEqual(len(macro.links()), 2)
        self.assertEqual(len(macro.annotations()), 1)

    def test_properties_restore(self):
        def load(stream):
            wf = Scheme()
            reg = foo_registry()
            readwrite.scheme_load(wf, stream, reg)
            return wf

        workflow = load(io.BytesIO(FOOBAR_v30.encode()))
        root = workflow.root()
        nodes = root.nodes()
        n1, n2 = nodes[0], nodes[1]
        self.assertEqual(n1.properties, {"id": 1})
        self.assertEqual(n2.properties, {"id": 2})
        meta = nodes[2]
        assert isinstance(meta, MetaNode)
        n6 = meta.nodes()[2]
        assert n6.properties == {"id": 6}

        n6.properties = {"id": 6, "x": "1"}
        n2.properties = {"id": 2, "x": "2"}
        n1.properties = {"id": 1, "x": "3"}

        buffer = io.BytesIO()
        readwrite.scheme_to_ows_stream(workflow, buffer, pretty=True)
        buffer.seek(0)
        workflow = load(buffer)

        root = workflow.root()
        nodes = root.nodes()
        n1, n2 = nodes[0], nodes[1]
        self.assertEqual(n1.properties, {"id": 1, "x": "3"})
        self.assertEqual(n2.properties, {"id": 2, "x": "2"})
        meta = nodes[2]
        assert isinstance(meta, MetaNode)
        n6 = meta.nodes()[2]
        self.assertEqual(n6.properties, {"id": 6, "x": "1"})


def foo_registry():
    reg = WidgetRegistry()
    reg.register_category(CategoryDescription("Quack"))
    reg.register_widget(
        WidgetDescription(
            name="Foo",
            id="foooo",
            qualified_name="package.foo",
            project_name="Foo",
            category="Quack",
            inputs=[InputSignal("foo", object,)],
            outputs=[OutputSignal("foo", object)],
        )
    )
    reg.register_widget(
        WidgetDescription(
            name="Bar",
            id="barrr",
            qualified_name="frob.bar",
            project_name="Bar",
            replaces=["package.bar"],
            category="Quack",
            inputs=[InputSignal("bar", object, )],
            outputs=[OutputSignal("bar", object)],
        )
    )
    return reg


FOOBAR_v20 = """<?xml version="1.0" ?>
<scheme title="FooBar" description="Foo to the bar" version="2.0">
    <nodes>
        <node id="0" title="Foo" position="1, 2" project_name="Foo"
              qualified_name="package.foo" />
        <node id="1" title="Bar" position="2, 3" project_name="Foo"
              qualified_name="package.bar" />
    </nodes>
    <links>
        <link enabled="true" id="0" sink_channel="bar" sink_node_id="1"
              source_channel="foo" source_node_id="0" />
        <link enabled="false" id="1" sink_channel="bar1" sink_node_id="1"
              source_channel="foo1" source_node_id="0" />
    </links>
</scheme>
"""

FOOBAR_v30 = """<?xml version="1.0" ?>
<scheme title="FooBar" description="Foo to the bar" version="3.0">
    <nodes>
        <node id="1" title="Foo" position="1, 2" project_name="Foo"
              qualified_name="package.foo" />
        <node id="2" title="Bar" position="2, 3" project_name="Foo"
              qualified_name="package.bar" />
        <macro_node id="3" title="Frobnicate" position="3, 3" >
            <nodes>
                <input_node id="4" title="In" type="object" position="1, 1" />
                <output_node id="5" title="Out" type="object" position="1, 2" />
                <node id="6" title="Baz" position="1, 3" project_name="Foo"
                      qualified_name="package.bar" />
            </nodes>
            <links>
                <link id="1" enabled="true"
                      source_node_id="4" source_channel="In"
                      sink_node_id="6" sink_channel="bar" />
                <link id="2" enabled="true"
                      source_node_id="6" source_channel="bar"
                      sink_node_id="5" sink_channel="Out" />
            </links>
            <annotations>
                <text geometry="1, 1, 3, 3" >This is a Baz</text>
            </annotations>
        </macro_node>
    </nodes>
    <links>
        <link id="3" enabled="true" sink_channel="In" sink_node_id="3"
              source_channel="foo" source_node_id="1" />
        <link id="4" enabled="true" sink_channel="bar" sink_node_id="2"
              source_channel="Out" source_node_id="3" />
    </links>
    <node_properties>
        <properties node_id="1" format="literal">{"id": 1}</properties>
        <properties node_id="2" format="literal">{"id": 2}</properties>
        <properties node_id="6" format="literal">{"id": 6}</properties>
    </node_properties>
</scheme>
"""
