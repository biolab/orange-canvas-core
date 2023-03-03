import unittest

from pkg_resources import Requirement

from orangecanvas.application.utils.addons import (
    Available,
    Installable,
    Installed,
    installable_from_json_response,
    installable_items,
    is_updatable,
    prettify_name,
)
from orangecanvas.config import Distribution


class TestUtils(unittest.TestCase):
    def test_items_1(self):
        inst = Installable("foo", "1.0", "a foo", "", "", [])
        dist = Distribution(project_name="foo", version="1.0")
        item = Available(inst)
        self.assertFalse(is_updatable(item))

        item = Installed(None, dist)
        self.assertFalse(is_updatable(item))
        item = Installed(inst, dist)
        self.assertFalse(is_updatable(item))

        item = Installed(inst._replace(version="0.9"), dist)
        self.assertFalse(is_updatable(item))

        item = Installed(inst._replace(version="1.1"), dist)
        self.assertTrue(is_updatable(item))

        item = Installed(inst._replace(version="2.0"), dist,
                         constraint=Requirement.parse("foo<1.99"))
        self.assertFalse(is_updatable(item))
        item = Installed(inst._replace(version="2.0"), dist,
                         constraint=Requirement.parse("foo<2.99"))
        self.assertTrue(is_updatable(item))

    def test_items_2(self):
        inst1 = Installable("foo", "1.0", "a foo", "", "", [])
        inst2 = Installable("bar", "1.0", "a bar", "", "", [])
        dist2 = Distribution(project_name="bar", version="0.9")
        dist3 = Distribution(project_name="quack", version="1.0")
        items = installable_items([inst1, inst2], [dist2, dist3])
        self.assertIn(Available(inst1), items)
        self.assertIn(Installed(inst2, dist2), items)
        self.assertIn(Installed(None, dist3), items)

    def test_installable_from_json_response(self):
        inst = installable_from_json_response({
            "info": {
                "name": "foo",
                "version": "1.0",
            },
            "releases": {
                "1.0": [
                    {
                        "filename": "aa.tar.gz",
                        "url": "https://examples.com",
                        "size": 100,
                        "packagetype": "sdist",
                    }
                ]
            },
        })
        self.assertTrue(inst.name, "foo")
        self.assertEqual(inst.version, "1.0")

    def test_prettify_name(self):
        names = [
            'AFooBar', 'FooBar', 'Foo-Bar', 'Foo-Bar-FOOBAR',
            'Foo-bar-foobar', 'Foo', 'FOOBar', 'A4FooBar',
            '4Foo', 'Foo3Bar'
        ]
        pretty_names = [
            'A Foo Bar', 'Foo Bar', 'Foo Bar', 'Foo Bar FOOBAR',
            'Foo bar foobar', 'Foo', 'FOO Bar', 'A4Foo Bar',
            '4Foo', 'Foo3Bar'
        ]

        for name, pretty_name in zip(names, pretty_names):
            self.assertEqual(pretty_name, prettify_name(name))

        # test if orange prefix is handled
        self.assertEqual('Orange', prettify_name('Orange'))
        self.assertEqual('Orange3', prettify_name('Orange3'))
        self.assertEqual('Some Addon', prettify_name('Orange-SomeAddon'))
        self.assertEqual('Text', prettify_name('Orange3-Text'))
        self.assertEqual('Image Analytics', prettify_name('Orange3-ImageAnalytics'))
        self.assertEqual('Survival Analysis', prettify_name('Orange3-Survival-Analysis'))


if __name__ == "__main__":
    unittest.main()
