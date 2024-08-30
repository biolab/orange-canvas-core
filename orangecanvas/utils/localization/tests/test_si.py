import os
import sys
import unittest

# This test will usually not be run when the module `si` is embedded within
# Orange structure, hence we manually insert its path
from itertools import chain

si_path = os.path.join(os.path.dirname(__file__), "..")
sys.path.append(si_path)
from si import plsi, plsi_sz, z_besedo


class TestPlsi(unittest.TestCase):
    def test_plsi_4(self):
        self.assertEqual(plsi(0, "okno|okni|okna|oken"), "oken")
        self.assertEqual(plsi(1, "okno|okni|okna|oken"), "okno")
        self.assertEqual(plsi(2, "okno|okni|okna|oken"), "okni")
        self.assertEqual(plsi(3, "okno|okni|okna|oken"), "okna")
        self.assertEqual(plsi(4, "okno|okni|okna|oken"), "okna")
        self.assertEqual(plsi(5, "okno|okni|okna|oken"), "oken")
        self.assertEqual(plsi(11, "okno|okni|okna|oken"), "oken")
        self.assertEqual(plsi(100, "okno|okni|okna|oken"), "oken")
        self.assertEqual(plsi(101, "okno|okni|okna|oken"), "okno")
        self.assertEqual(plsi(102, "okno|okni|okna|oken"), "okni")
        self.assertEqual(plsi(103, "okno|okni|okna|oken"), "okna")
        self.assertEqual(plsi(105, "okno|okni|okna|oken"), "oken")
        self.assertEqual(plsi(1001, "okno|okni|okna|oken"), "okno")

    def test_plsi_3(self):
        self.assertEqual(plsi(0, "oknu|oknoma|oknom"), "oknom")
        self.assertEqual(plsi(1, "oknu|oknoma|oknom"), "oknu")
        self.assertEqual(plsi(2, "oknu|oknoma|oknom"), "oknoma")
        self.assertEqual(plsi(3, "oknu|oknoma|oknom"), "oknom")
        self.assertEqual(plsi(5, "oknu|oknoma|oknom"), "oknom")
        self.assertEqual(plsi(1, "oknu|oknoma|oknom"), "oknu")
        self.assertEqual(plsi(105, "oknu|oknoma|oknom"), "oknom")

    def test_plsi_1(self):
        self.assertEqual(plsi(0, "miza"), "miz")
        self.assertEqual(plsi(1, "miza"), "miza")
        self.assertEqual(plsi(2, "miza"), "mizi")
        self.assertEqual(plsi(3, "miza"), "mize")
        self.assertEqual(plsi(5, "miza"), "miz")
        self.assertEqual(plsi(101, "miza"), "miza")
        self.assertEqual(plsi(105, "miza"), "miz")

        self.assertEqual(plsi(0, "primer"), "primerov")
        self.assertEqual(plsi(1, "primer"), "primer")
        self.assertEqual(plsi(2, "primer"), "primera")
        self.assertEqual(plsi(3, "primer"), "primeri")
        self.assertEqual(plsi(5, "primer"), "primerov")
        self.assertEqual(plsi(50, "primer"), "primerov")
        self.assertEqual(plsi(101, "primer"), "primer")
        self.assertEqual(plsi(105, "primer"), "primerov")


class TestPlsi_si(unittest.TestCase):
    def test_plsi_sz(self):
        for propn in "z0 z1 z2 s3 s4 s5 s6 s7 z8 z9 z10 " \
                      "z11 z12 s13 s14 s15 s16 s17 z18 z19 z20 " \
                      "z21 z22 s23 z31 z32 s35 s40 s50 s60 s70 z80 z90 " \
                      "z200 z22334 s3943 z832492 " \
                      "s100 s108 s1000 s13333 s122222 z1000000 " \
                      "z1000000000 z1000000000000".split():
            self.assertEqual(plsi_sz(int(propn[1:])), propn[0], propn)


class TestZBesedo(unittest.TestCase):
    def test_z_besedo(self):
        self.assertEqual(
            "\n".join(
                f"{z_besedo(n, 1, 'n')} "
                f"{plsi(n, 'zeleno drevo|zeleni drevesi|zelena drevesa|zelenih dreves')}"
                for n in chain(range(6), (11, ))),
            """nič zelenih dreves
eno zeleno drevo
dve zeleni drevesi
tri zelena drevesa
štiri zelena drevesa
pet zelenih dreves
11 zelenih dreves"""
        )

        self.assertEqual(
            "\n".join(
                f"{plsi_sz(n).upper()} {z_besedo(n, 6, 'n')} "
                f"{plsi(n, 'zelenim drevesom|zelenima drevesoma|zelenimi drevesi')}"
                for n in chain(range(1, 6), (11, 100, 101))),
            """Z enim zelenim drevesom
Z dvema zelenima drevesoma
S tremi zelenimi drevesi
S štirimi zelenimi drevesi
S petimi zelenimi drevesi
Z 11 zelenimi drevesi
S 100 zelenimi drevesi
S 101 zelenim drevesom""")

        self.assertEqual(f"{z_besedo(0, 1, 'm', 'brez')} {plsi(0, 'drevesa|dreves|dreves')}",
                         "brez dreves")


sys.path.remove(si_path)

if __name__ == "__main__":
    unittest.main()
