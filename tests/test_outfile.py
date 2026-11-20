"""Tests of the .out reader and of `reread`, on real engine output.

tests/data/tiny.inp has three junctions, an outfall, a storage node, three conduits and a pump. Two engines ran it:
tests/data/tiny.out is from swmm5-rust (EPA SWMM 5.2.4 in Rust, byte-identical to EPA on its gates) and
tests/data/tiny_openswmm6.out from swmm6-rust (OpenSWMM 6 in Rust, byte-identical to the C++ on its gates). What
the reader must say is fixed by that input file, not by the reader.

    python3 -m unittest discover -s tests

Written by Claude (Anthropic) for Robert Dickinson; see AI-USE.md.
"""
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from swmmrr import outfile, record          # noqa: E402

INP = os.path.join(HERE, 'data', 'tiny.inp')
OUT = os.path.join(HERE, 'data', 'tiny.out')
OUT_SHA256 = '52f9d88e4ee5f7704ada470cc9083483c183a3a2da3ba976cf522f7502e814b2'
OUT6 = os.path.join(HERE, 'data', 'tiny_openswmm6.out')


def inp_types(path):
    """{name: type} for nodes and for links, by the section of the input file each one is in."""
    nodes, links, section = {}, {}, None
    node_sections = {'[JUNCTIONS]': 'JUNCTION', '[OUTFALLS]': 'OUTFALL', '[STORAGE]': 'STORAGE', '[DIVIDERS]': 'DIVIDER'}
    link_sections = {'[CONDUITS]': 'CONDUIT', '[PUMPS]': 'PUMP', '[ORIFICES]': 'ORIFICE', '[WEIRS]': 'WEIR',
                     '[OUTLETS]': 'OUTLET'}
    with open(path, encoding='latin-1') as fh:
        for line in fh:
            line = line.split(';')[0].strip()
            if line.startswith('['):
                section = line.upper()
            elif line and section in node_sections:
                nodes[line.split()[0]] = node_sections[section]
            elif line and section in link_sections:
                links[line.split()[0]] = link_sections[section]
    return nodes, links


class Reader(unittest.TestCase):
    def setUp(self):
        with open(OUT, 'rb') as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), OUT_SHA256, 'the fixture has changed')
        self.o = outfile.OutFile(OUT)

    def test_types_are_the_input_files(self):
        nodes, links = inp_types(INP)
        self.assertEqual({n: self.o.node_type(i) for i, n in enumerate(self.o.nodes)}, nodes)
        self.assertEqual({n: self.o.link_type(i) for i, n in enumerate(self.o.links)}, links)
        # and they are not all the first type, which is what reading the code as a float gives
        self.assertEqual(sorted(set(nodes.values())), ['JUNCTION', 'OUTFALL', 'STORAGE'])
        self.assertEqual(sorted(set(links.values())), ['CONDUIT', 'PUMP'])

    def test_type_code_is_stored_as_an_integer(self):
        """The bytes themselves: O1's type is the INT4 1, which as a REAL4 is 1.4e-45."""
        codes, _ = self.o.props['node']
        self.assertEqual(codes, [0, 2, 3])
        nsv = 1 + 1 + self.o.nsub                     # count, one code, one area per subcatchment
        p = self.o.input_pos + 4 * nsv + 4 * (1 + len(codes)) + 4 * len(codes) * self.o.nodes.index('O1')
        self.assertEqual(struct.unpack_from('<i', self.o.b, p)[0], 1)
        self.assertLess(struct.unpack_from('<f', self.o.b, p)[0], 1e-40)

    def test_other_properties_are_the_input_files(self):
        codes, rows = self.o.props['node']
        j1 = rows[self.o.nodes.index('J1')]
        self.assertEqual((j1[codes.index(2)], j1[codes.index(3)]), (100.0, 10.0))        # invert, max depth
        codes, rows = self.o.props['link']
        c1 = rows[self.o.links.index('C1')]
        self.assertEqual((c1[3], c1[4]), (1.5, 400.0))                                   # max depth, length
        self.assertEqual(self.o.props['sub'][1][0], (1.0,))                              # area

    def test_values_the_model_fixes(self):
        self.assertEqual((self.o.nperiods, self.o.report_step), (120, 60))
        pump = self.o.series('link', self.o.links.index('P1'), 0)
        self.assertEqual(sorted(set(pump)), [0.0, 5.0])                                  # the curve: 5 cfs or off
        c1 = self.o.series('link', self.o.links.index('C1'), 0)
        self.assertAlmostEqual(c1[-1], 1.0, delta=0.01)                                  # the steady inflow


class ReaderOpenSwmm6(unittest.TestCase):
    """OpenSWMM 6 numbers STORAGE and DIVIDER the other way round, and writes its own numbers."""

    def setUp(self):
        self.o = outfile.OutFile(OUT6)

    def test_it_is_an_openswmm6_file_of_the_same_model(self):
        five = outfile.OutFile(OUT)
        self.assertEqual(self.o.version, 60000)
        self.assertEqual((self.o.nodes, self.o.links, self.o.subcatchments), (five.nodes, five.links, five.subcatchments))

    def test_types_are_the_input_files(self):
        nodes, links = inp_types(INP)
        self.assertEqual({n: self.o.node_type(i) for i, n in enumerate(self.o.nodes)}, nodes)
        self.assertEqual({n: self.o.link_type(i) for i, n in enumerate(self.o.links)}, links)

    def test_the_storage_node_carries_swmm5s_divider_code(self):
        codes, rows = self.o.props['node']
        self.assertEqual(rows[self.o.nodes.index('WET1')][codes.index(0)], 3)
        five = outfile.OutFile(OUT)
        codes5, rows5 = five.props['node']
        self.assertEqual(rows5[five.nodes.index('WET1')][codes5.index(0)], 2)

    def test_properties_are_in_swmm5s_order_under_other_code_numbers(self):
        five = outfile.OutFile(OUT)
        self.assertEqual((five.props['node'][0], five.props['link'][0]), ([0, 2, 3], [0, 4, 4, 3, 5]))
        self.assertEqual((self.o.props['node'][0], self.o.props['link'][0]), ([0, 2, 4], [0, 6, 7, 4, 8]))
        for kind in ('sub', 'link'):
            self.assertEqual(self.o.props[kind][1], five.props[kind][1])
        # nodes: the same values but the type code
        self.assertEqual([r[1:] for r in self.o.props['node'][1]], [r[1:] for r in five.props['node'][1]])


class Reread(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        o = outfile.OutFile(OUT)
        rec = dict(schema=record.SCHEMA, files=dict(out=dict(sha256=OUT_SHA256)), **record._out_sections(o))
        # a record as the reader before 1.0.1 made it: every node a JUNCTION, every link a CONDUIT
        rec['objects']['node_types'] = {'JUNCTION': o.nnode}
        rec['objects']['link_types'] = {'CONDUIT': o.nlink}
        for d in rec['peaks']['nodes'].values():
            d['type'] = 'JUNCTION'
        for d in rec['peaks']['links'].values():
            d['type'] = 'CONDUIT'
        self.path = os.path.join(self.dir, 'record.json')
        with open(self.path, 'w') as fh:
            json.dump(record.clean(rec), fh)
        self.before = json.loads(json.dumps(record.clean(rec)))

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_corrects_the_types_and_nothing_else(self):
        rec, changed = record.reread(self.path, OUT, 'test')
        # two nodes (O1, WET1) and one link (P1) change type, and with them the counts of each type
        self.assertEqual(changed, {'objects.node_types.JUNCTION': 1, 'objects.node_types.OUTFALL': 1,
                                   'objects.node_types.STORAGE': 1, 'objects.link_types.CONDUIT': 1,
                                   'objects.link_types.PUMP': 1, 'peaks.nodes.*.type': 2, 'peaks.links.*.type': 1})
        self.assertEqual(rec['objects']['node_types'], {'JUNCTION': 3, 'OUTFALL': 1, 'STORAGE': 1})
        self.assertEqual(rec['objects']['link_types'], {'CONDUIT': 3, 'PUMP': 1})
        self.assertEqual(rec['peaks']['nodes']['WET1']['type'], 'STORAGE')
        self.assertEqual(rec['peaks']['links']['P1']['type'], 'PUMP')
        # every number is as it was
        for kind in ('subcatchments', 'nodes', 'links', 'system'):
            for name, d in rec['peaks'][kind].items():
                for k, v in d.items():
                    if k != 'type':
                        self.assertEqual(v, self.before['peaks'][kind][name][k])
        self.assertEqual(rec['summary'], self.before['summary'])
        c = rec['corrections'][-1]
        self.assertEqual((c['out_sha256'], c['reason'], c['changed']), (OUT_SHA256, 'test', dict(sorted(changed.items()))))
        with open(self.path) as fh:
            self.assertEqual(json.load(fh), json.loads(json.dumps(record.clean(rec))))

    def test_a_second_reread_changes_nothing(self):
        record.reread(self.path, OUT, 'test')
        rec, changed = record.reread(self.path, OUT, 'again')
        self.assertEqual(changed, {})
        self.assertEqual(len(rec['corrections']), 1)

    def test_another_file_is_refused(self):
        other = os.path.join(self.dir, 'other.out')
        with open(OUT, 'rb') as fh:
            b = bytearray(fh.read())
        b[-30] ^= 1                                    # one bit, in the last period
        with open(other, 'wb') as fh:
            fh.write(b)
        with self.assertRaises(ValueError):
            record.reread(self.path, other, 'test')
        with open(self.path) as fh:
            self.assertEqual(json.load(fh), self.before)


if __name__ == '__main__':
    unittest.main()
