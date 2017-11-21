import unittest
import io

from ..scanner import preview_parse, filter_properties

test_ows = b"""\
<?xml version="1.0" encoding="utf-8"?>
<scheme title="Football" description="On this sunday" version="2.0" >
 <nodes>
  <node id="0" name="A" position="(152.0, 158.0)" />
  <node id="1" name="B" position="(316.0, 163.0)" />
  <node id="2" name="C" position="(166.0, 265.0)" />
  <node id="3" name="D" position="(459.0, 158.0)" />
 </nodes>
 <links>
  <link enabled="true" id="0" sink_channel="B.1" sink_node_id="1" source_channel="A.1" source_node_id="0" />
  <link enabled="true" id="1" sink_channel="B.2" sink_node_id="1" source_channel="B.1" source_node_id="2" />
  <link enabled="true" id="2" sink_channel="C.1" sink_node_id="3" source_channel="B.1" source_node_id="1" />
 </links>
 <node_properties>
  <properties format="pickle" node_id="0">random garbage</properties>
  <properties format="pickle" node_id="1">random garbage</properties>
 </node_properties>
</scheme>
"""


class TestPreviewParse(unittest.TestCase):
    def test_filter_properties(self):
        stream = io.BytesIO(test_ows)
        filtered = filter_properties(stream)
        self.assertNotIn(b'<properties>', filtered)
        self.assertEqual(filtered.count(b'<node '), 4)

    def test_preview_parse(self):
        stream = io.BytesIO(test_ows)
        a, b, c = preview_parse(stream)
        assert a == "Football"
        assert b == "On this sunday"
        assert c == ""
