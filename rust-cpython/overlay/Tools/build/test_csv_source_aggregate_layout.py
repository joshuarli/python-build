import struct
import unittest
from unittest import mock
import csv_source_aggregate_layout as layout


def image(const_size=16384, data_size=16384, const_flags=16, data_prot=3,
          extra=False, section_size=24, section_alignment=3, section_flags=0):
    commands = []
    cursor = 0
    for name, size, prot, flags in [('__TEXT', 16384, 5, 0),
                                   ('__DATA_CONST', const_size, 3, const_flags),
                                   ('__DATA', data_size, data_prot, 0),
                                   ('__LINKEDIT', 16384, 1, 0)] + ([('__OTHER', 16384, 3, 0)] if extra else []):
        section = name in ('__DATA_CONST', '__DATA')
        command_size = 152 if section else 72
        command = struct.pack('<II16sQQQQiiII', 25, command_size, name.encode(),
                              cursor, size, cursor, size, prot, prot, int(section), flags)
        if section:
            command += struct.pack('<16s16sQQIIIIIIII', b'__const' if name == '__DATA_CONST' else b'__thread_bss',
                                   name.encode(), cursor, section_size, cursor,
                                   section_alignment, 0, 0, section_flags, 0, 0, 0)
        commands.append(command)
        cursor += size
    header = struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 6, len(commands),
                         sum(map(len, commands)), 0x80, 0)
    blob = header + b''.join(commands)
    return blob + bytes(max(cursor - len(blob), 0))


def linked_image():
    blob = bytearray(image())
    count, length = struct.unpack_from('<II', blob, 16)
    def dylib(tag, name):
        value = name.encode() + b'\0'
        size = (24 + len(value) + 7) & ~7
        return struct.pack('<6I', tag, size, 24, 0, 0, 0) + value + bytes(size - 24 - len(value))
    def leb(value):
        out = bytearray()
        while value >= 128:
            out.append((value & 127) | 128); value >>= 7
        out.append(value)
        return bytes(out)
    names = sorted(layout.INIT_EXPORTS)
    root_size = 0
    while True:
        trie_root = b'\0' + bytes([len(names)]) + b''.join(name.encode() + b'\0' + leb(root_size + index * 4)
                                                              for index, name in enumerate(names))
        if len(trie_root) == root_size: break
        root_size = len(trie_root)
    trie = trie_root + b'\2\0\0\0' * len(names)
    extra = (dylib(13, '@rpath/aggregate.dylib') + dylib(12, '/usr/lib/libSystem.B.dylib')
             + struct.pack('<4I', 0x80000033, 16, 49152, len(trie)))
    blob[32 + length:32 + length + len(extra)] = extra
    struct.pack_into('<II', blob, 16, count + 3, length + len(extra))
    blob[49152:49152 + len(trie)] = trie
    return bytes(blob)


class LayoutTests(unittest.TestCase):
    def surface(self):
        return {'loads': ['/usr/lib/libSystem.B.dylib'], 'exports': dict.fromkeys(layout.INIT_EXPORTS, 0),
                'imports': [], 'install_id': '@rpath/aggregate.dylib'}

    def check(self, blob, surface=None):
        with mock.patch.object(layout.csv_source_std, 'macho_link_surface', return_value=surface or self.surface()):
            return layout.verify_aggregate_layout(blob)

    def test_requires_exact_eleven_initializer_contract_and_schema_two(self):
        expected = {'_PyInit__' + name + '_rs' for name in
                    ('csv', 'json', 'typing', 'tokenize', 'datetime', 'threading', 'uuid',
                     'collections', 'sqlite3', 'warnings', 'socket')}
        self.assertEqual(layout.INIT_EXPORTS, expected)
        surface = self.surface()
        surface['exports'] = dict.fromkeys(expected, 0)
        proof = self.check(image(), surface)
        self.assertEqual(proof['schema'], 2)
        for name in ('collections', 'sqlite3', 'warnings', 'socket'):
            with self.subTest(helper=name):
                missing = self.surface()
                missing['exports'] = dict.fromkeys(expected - {'_PyInit__' + name + '_rs'}, 0)
                with self.assertRaisesRegex(ValueError, 'strong initializers'):
                    self.check(image(), missing)

    def test_rejects_weak_new_initializer(self):
        surface = self.surface()
        surface['exports']['_PyInit__socket_rs'] = 4
        with self.assertRaisesRegex(ValueError, 'strong initializers'):
            self.check(image(), surface)

    def test_retains_tls_bss_inventory_and_exact_page_boundary(self):
        proof = self.check(image(section_flags=0x12))
        self.assertEqual(proof['segments']['__DATA']['sections'][0]['type'], 0x12)
        self.assertEqual(proof['segments']['__DATA']['span_bytes'], 24)
        self.assertEqual(proof['segments']['__DATA_CONST']['vmsize'], 16384)

    def test_rejects_lost_const_protection_and_executable_data(self):
        for blob in (image(const_flags=0), image(data_prot=7)):
            with self.assertRaises(ValueError): self.check(blob)

    def test_rejects_extra_writable_segment_and_over_budget_span(self):
        for blob in (image(extra=True), image(const_size=32768), image(data_size=32768), image(section_size=16385)):
            with self.assertRaises(ValueError): self.check(blob)

    def test_rejects_bad_section_alignment_and_file_extent(self):
        for blob in (image(section_alignment=64), image(section_size=20000)):
            with self.assertRaises(ValueError): self.check(blob)

    def test_rejects_provider_load_duplicate_load_and_extra_initializer(self):
        for mutate in (lambda s: s['loads'].append('@rpath/libstd-x.dylib'),
                       lambda s: s['loads'].append('/usr/lib/libSystem.B.dylib'),
                       lambda s: s['exports'].update({'_PyInit__pathlib_rs': 0})):
            surface = self.surface(); mutate(surface)
            with self.assertRaises(ValueError): self.check(image(), surface)

    def test_real_link_surface_and_layout_are_checked_together(self):
        proof = layout.verify_aggregate_layout(linked_image())
        self.assertEqual(set(proof['link_surface']['exports']), layout.INIT_EXPORTS)
        self.assertEqual(proof['link_surface']['loads'], ['/usr/lib/libSystem.B.dylib'])

    def test_rejects_overlapping_duplicate_and_foreign_section_ownership(self):
        for change in ('segment', 'section'):
            blob = bytearray(image())
            if change == 'segment':
                struct.pack_into('<Q', blob, 32 + 72 + 24, 0)
            else:
                blob[32 + 72 + 72 + 16:32 + 72 + 72 + 32] = b'__DATA'.ljust(16, b'\0')
            with self.assertRaises(ValueError): self.check(bytes(blob))

    def test_existing_surface_parser_rejects_wrong_architecture(self):
        blob = bytearray(image()); struct.pack_into('<I', blob, 4, 7)
        with self.assertRaises(ValueError): layout.verify_aggregate_layout(bytes(blob))


if __name__ == '__main__': unittest.main()
