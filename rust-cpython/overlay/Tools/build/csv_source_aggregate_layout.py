"""Verify the protected and writable page budget of the eleven-helper image."""
import _struct as struct
import csv_source_std

PAGE_SIZE = 16384
INIT_EXPORTS = frozenset('_PyInit__' + name + '_rs' for name in
                         ('csv', 'json', 'typing', 'tokenize', 'datetime', 'threading', 'uuid',
                          'collections', 'sqlite3', 'warnings', 'socket'))


def verify_aggregate_layout(data: bytes) -> dict:
    """Retain every section in the proof; mapped spans, not payload sums, bind the budget.

    Relocated constant data remains protected after dyld fixups. TLS, zero-fill,
    compiler metadata and module definitions are counted rather than discarded.
    The existing link parser supplies the strict architecture and binding checks.
    """
    surface = csv_source_std.macho_link_surface(data)
    def require(condition, message):
        if not condition:
            raise ValueError('aggregate layout: ' + message)
    require(surface['loads'] == ['/usr/lib/libSystem.B.dylib'], 'expected only System dependency')
    initializers = {name for name in surface['exports'] if name.startswith('_PyInit_')}
    require(initializers == INIT_EXPORTS and all(surface['exports'][name] == 0 for name in INIT_EXPORTS),
            'expected eleven strong initializers')
    require(struct.unpack_from('<I', data, 8)[0] == 0, 'expected arm64 subtype')
    count, length = struct.unpack_from('<II', data, 16)
    end, position = 32 + length, 32
    segments = {}
    ranges = []
    for _ in range(count):
        tag, size = struct.unpack_from('<II', data, position)
        if tag == 25:
            name = data[position + 8:position + 24].split(b'\0')[0].decode('ascii')
            require(name in ('__TEXT', '__DATA_CONST', '__DATA', '__LINKEDIT') and name not in segments,
                    'unknown or duplicate segment')
            vmaddr, vmsize, fileoff, filesize, maximum, initial, section_count, flags = struct.unpack_from('<4Q4I', data, position + 24)
            require(vmsize > 0 and vmaddr % PAGE_SIZE == 0 and vmsize % PAGE_SIZE == 0
                    and filesize <= vmsize, 'segment mapping extent')
            require(not any(vmaddr < right and left < vmaddr + vmsize for left, right in ranges),
                    'overlapping segments')
            ranges.append((vmaddr, vmaddr + vmsize))
            if name == '__DATA_CONST':
                require(initial in (1, 3) and maximum == 3 and flags == 16,
                        'constant data lost read-only-after-fixup protection')
            elif name == '__DATA':
                require(initial == 3 and maximum == 3 and flags == 0, 'writable data protection')
            elif name == '__TEXT':
                require(initial == 5 and maximum in (5, 7) and flags == 0, 'text protection')
            else:
                require(initial == 1 and maximum in (1, 7) and flags == 0, 'linkedit protection')
            if name in ('__DATA_CONST', '__DATA'):
                require(vmsize <= PAGE_SIZE, 'data segment exceeds one page')
            sections, section_ranges, section_names = [], [], set()
            for index in range(section_count):
                offset = position + 72 + index * 80
                section_name = data[offset:offset + 16].split(b'\0')[0].decode('ascii')
                owner = data[offset + 16:offset + 32].split(b'\0')[0].decode('ascii')
                address, extent, file_offset, alignment, reloc_offset, reloc_count, section_flags, _, _, _ = struct.unpack_from('<2Q8I', data, offset + 32)
                require(owner == name and section_name and section_name not in section_names, 'section ownership')
                section_names.add(section_name)
                require(alignment < 64 and address % (1 << alignment) == 0
                        and vmaddr <= address <= address + extent <= vmaddr + vmsize,
                        'section alignment or mapped extent')
                require(not any(address < right and left < address + extent for left, right in section_ranges),
                        'overlapping sections')
                section_ranges.append((address, address + extent))
                if name in ('__DATA_CONST', '__DATA'):
                    require(not section_flags & 0x80000400, 'instructions in data section')
                section_type = section_flags & 255
                if section_type not in (1, 12, 18):
                    require(fileoff <= file_offset <= file_offset + extent <= fileoff + filesize,
                            'section file extent')
                require(reloc_count == 0 or reloc_offset + reloc_count * 8 <= len(data), 'section relocation extent')
                sections.append({'name': section_name, 'address': address, 'size': extent,
                                 'alignment': alignment, 'type': section_type, 'flags': section_flags})
            if name in ('__DATA_CONST', '__DATA'):
                require(bool(sections), 'empty data section inventory')
            span = max((right for _, right in section_ranges), default=vmaddr) - vmaddr
            segments[name] = {'vmaddr': vmaddr, 'vmsize': vmsize, 'filesize': filesize,
                              'maxprot': maximum, 'initprot': initial, 'flags': flags,
                              'sections': sections, 'payload_bytes': sum(row['size'] for row in sections),
                              'span_bytes': span}
        position += size
    require(position == end and set(segments) == {'__TEXT', '__DATA_CONST', '__DATA', '__LINKEDIT'},
            'required segment inventory')
    return {'schema': 2, 'page_size': PAGE_SIZE, 'segments': segments, 'link_surface': surface}
