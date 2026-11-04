"""outfile.py - reader for the binary output (.out) file of EPA SWMM 5 and of OpenSWMM 6.

Both engines write the same layout (SWMM 5's), with a different version number in the header (5.2.4 writes 52004,
OpenSWMM 6 writes 60000) and, for OpenSWMM 6, possibly more reporting variables. The reader therefore takes every
count from the file itself (property codes, variable codes) instead of assuming SWMM 5's, and names the variable
codes it knows.

Written by Claude (Anthropic) for Robert Dickinson; see AI-USE.md.
"""
import hashlib
import struct

MAGIC = 516114522
FLOW_UNITS = ['CFS', 'GPM', 'MGD', 'CMS', 'LPS', 'MLD']          # the .out header's flow-unit code
US_FLOW_UNITS = ('CFS', 'GPM', 'MGD')

# Variable names by code, for each object kind (SWMM 5.2 Interfacing Guide). Codes past these are water-quality
# variables (one per pollutant, in pollutant order) or variables this reader does not know (named code_N).
SUB_VARS = ['rainfall', 'snow_depth', 'evaporation_loss', 'infiltration_loss', 'runoff', 'groundwater_flow',
            'groundwater_elevation', 'soil_moisture']
NODE_VARS = ['depth', 'head', 'volume', 'lateral_inflow', 'total_inflow', 'flooding']
LINK_VARS = ['flow', 'depth', 'velocity', 'volume', 'capacity']
SYS_VARS = ['air_temperature', 'rainfall', 'snow_depth', 'infiltration', 'runoff', 'dry_weather_inflow',
            'groundwater_inflow', 'rdii_inflow', 'external_inflow', 'total_lateral_inflow', 'flooding',
            'outfall_outflow', 'storage_volume', 'evaporation', 'pet']
NODE_TYPES = ['JUNCTION', 'OUTFALL', 'STORAGE', 'DIVIDER']
LINK_TYPES = ['CONDUIT', 'PUMP', 'ORIFICE', 'WEIR', 'OUTLET']


class OutFile:
    """Read a SWMM .out file. Raises ValueError when the file is not a complete one."""

    def __init__(self, path):
        with open(path, 'rb') as fh:
            self.b = b = fh.read()
        if len(b) < 52:
            raise ValueError('too short to be a SWMM output file (%d bytes)' % len(b))
        head = struct.unpack_from('<7i', b, 0)
        tail = struct.unpack_from('<6i', b, len(b) - 24)
        if head[0] != MAGIC or tail[5] != MAGIC:
            raise ValueError('not a complete SWMM output file (magic numbers %d, %d)' % (head[0], tail[5]))
        self.version, fu = head[1], head[2]
        self.flow_units = FLOW_UNITS[fu] if 0 <= fu < len(FLOW_UNITS) else 'code_%d' % fu
        self.nsub, self.nnode, self.nlink, self.npoll = head[3:7]
        self.id_pos, self.input_pos, self.output_pos, self.nperiods, self.error_code = tail[:5]
        # object names, then the pollutants' concentration-unit codes
        p = self.id_pos
        names = []
        for _ in range(self.nsub + self.nnode + self.nlink + self.npoll):
            n = struct.unpack_from('<i', b, p)[0]
            names.append(b[p + 4:p + 4 + n].decode('latin-1'))
            p += 4 + n
        a, c, d = self.nsub, self.nsub + self.nnode, self.nsub + self.nnode + self.nlink
        self.subcatchments, self.nodes, self.links, self.pollutants = names[:a], names[a:c], names[c:d], names[d:]
        # object properties: for each kind a count, that many codes, then each object's values
        p = self.input_pos
        self.props = {}
        for kind, n in (('sub', self.nsub), ('node', self.nnode), ('link', self.nlink)):
            k = struct.unpack_from('<i', b, p)[0]
            codes = list(struct.unpack_from('<%di' % k, b, p + 4))
            p += 4 * (1 + k)
            vals = struct.unpack_from('<%df' % (k * n), b, p) if n else ()
            p += 4 * k * n
            self.props[kind] = (codes, [vals[i * k:(i + 1) * k] for i in range(n)])
        # reporting variables: for each kind a count and the codes
        self.var_codes = {}
        for kind in ('sub', 'node', 'link', 'sys'):
            k = struct.unpack_from('<i', b, p)[0]
            self.var_codes[kind] = list(struct.unpack_from('<%di' % k, b, p + 4))
            p += 4 * (1 + k)
        self.start_date = struct.unpack_from('<d', b, p)[0]      # days since 12/30/1899, as SWMM keeps dates
        self.report_step = struct.unpack_from('<i', b, p + 8)[0]  # seconds
        if p + 12 != self.output_pos:
            raise ValueError('layout check failed: results expected at byte %d, the file says %d' % (p + 12, self.output_pos))
        self.nsv, self.nnv, self.nlv, self.nyv = (len(self.var_codes[k]) for k in ('sub', 'node', 'link', 'sys'))
        self.period_bytes = 8 + 4 * (self.nsub * self.nsv + self.nnode * self.nnv + self.nlink * self.nlv + self.nyv)
        end = self.output_pos + self.nperiods * self.period_bytes
        if end > len(b) - 24:
            raise ValueError('results run past the end of the file (%d periods of %d bytes)' % (self.nperiods, self.period_bytes))

    @property
    def unit_system(self):
        return 'US' if self.flow_units in US_FLOW_UNITS else 'SI'

    def var_names(self, kind):
        """Names of the reporting variables of a kind ('sub', 'node', 'link', 'sys'), in file order."""
        base = {'sub': SUB_VARS, 'node': NODE_VARS, 'link': LINK_VARS, 'sys': SYS_VARS}[kind]
        out = []
        for code in self.var_codes[kind]:
            if code < len(base):
                out.append(base[code])
            elif kind != 'sys' and code - len(base) < self.npoll:
                out.append('quality:' + self.pollutants[code - len(base)])
            else:
                out.append('code_%d' % code)
        return out

    def node_type(self, i):
        codes, vals = self.props['node']
        t = int(vals[i][codes.index(0)]) if 0 in codes else -1
        return NODE_TYPES[t] if 0 <= t < len(NODE_TYPES) else 'code_%d' % t

    def link_type(self, i):
        codes, vals = self.props['link']
        t = int(vals[i][codes.index(0)]) if 0 in codes else -1
        return LINK_TYPES[t] if 0 <= t < len(LINK_TYPES) else 'code_%d' % t

    def results_sha256(self):
        """SHA-256 of the results block alone (every period's date and values), which two engines can share even
        when their headers differ (a version number, say)."""
        return hashlib.sha256(self.b[self.output_pos:self.output_pos + self.nperiods * self.period_bytes]).hexdigest()

    def dates(self):
        return [struct.unpack_from('<d', self.b, self.output_pos + k * self.period_bytes)[0] for k in range(self.nperiods)]

    def _offset(self, kind, index, var):
        if kind == 'sub':
            return 8 + 4 * (index * self.nsv + var)
        if kind == 'node':
            return 8 + 4 * (self.nsub * self.nsv + index * self.nnv + var)
        if kind == 'link':
            return 8 + 4 * (self.nsub * self.nsv + self.nnode * self.nnv + index * self.nlv + var)
        return 8 + 4 * (self.nsub * self.nsv + self.nnode * self.nnv + self.nlink * self.nlv + var)

    def series(self, kind, index, var):
        """One variable of one object over every reporting period (single-precision values, as stored)."""
        off = self.output_pos + self._offset(kind, index, var)
        pb = self.period_bytes
        return [struct.unpack_from('<f', self.b, off + k * pb)[0] for k in range(self.nperiods)]

    def period_values(self, k):
        """Every value of period k as one flat tuple (subcatchments, nodes, links, system), after the date."""
        n = (self.period_bytes - 8) // 4
        return struct.unpack_from('<%df' % n, self.b, self.output_pos + k * self.period_bytes + 8)
