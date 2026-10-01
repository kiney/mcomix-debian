import binascii
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock
import zlib

import gi
gi.require_version('Gtk', '3.0')

from mcomix.archive import rar_external, sevenzip_external, unrar_free
from mcomix.archive.unrar_free import UnrarFreeArchive


FIXTURES = Path(__file__).parent / 'fixtures'


def fixture(name, directory):
    """Decode libarchive 3.7.4 fixtures; license in COPYING.libarchive."""
    lines = (FIXTURES / (name + '.uu')).read_bytes().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(b'begin '))
    data = b''.join(binascii.a2b_uu(line) for line in lines[start + 1:]
                    if line and line != b'end')
    path = Path(directory) / name
    path.write_bytes(data)
    return str(path)


def stored_rar(path, entries, solid=False):
    """Create small RAR4 stored members to exercise unusual names/errors."""
    def header(kind, flags, payload):
        data = struct.pack('<BHH', kind, flags, 7 + len(payload)) + payload
        return struct.pack('<H', zlib.crc32(data) & 0xffff) + data

    data = b'Rar!\x1a\x07\x00' + header(0x73, 8 if solid else 0, b'\0' * 6)
    for name, content in entries:
        encoded = name.encode('ascii')
        directory = name.endswith('/')
        flags = 0x8000 | (0xe0 if directory else 0)
        if solid and name.startswith('page2'):
            flags |= 0x10
        payload = struct.pack('<IIBIIBBHI', len(content), len(content), 3,
                              zlib.crc32(content), 0, 20, 0x30,
                              len(encoded), 0o40755 if directory else 0o100644)
        data += header(0x74, flags, payload + encoded) + content
    data += header(0x7b, 0, b'')
    Path(path).write_bytes(data)
    return str(path)


class DetectionTest(unittest.TestCase):
    def test_7z_formats_alone_do_not_mean_rar_decoders_are_present(self):
        for codecs, expected in [(b'0 D 40303 Rar3\n0 D 40305 Rar5\n', True),
                                  (b'0 ED 21 LZMA2\n', False)]:
            info = b'Formats:\n0 ...F... Rar rar\nCodecs:\n' + codecs
            with self.subTest(codecs=codecs), \
                    mock.patch.object(sevenzip_external, '_7z_rar_available', None), \
                    mock.patch.object(sevenzip_external, '_7z_executable', '/7z'), \
                    mock.patch.object(sevenzip_external.subprocess, 'run') as run:
                run.return_value = subprocess.CompletedProcess([], 0, info, b'')
                self.assertEqual(sevenzip_external.RarArchive.is_available(), expected)

    def test_nonfree_handler_skips_relative_symlink_without_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            real = Path(directory) / 'unrar-free'
            real.write_text('#!/bin/sh\nexit 0\n')
            real.chmod(0o755)
            (Path(directory) / 'unrar').symlink_to('unrar-free')
            with mock.patch.dict(os.environ, {'PATH': directory}), \
                    mock.patch.object(rar_external, '_rar_executable', -1), \
                    mock.patch.object(rar_external.log, 'warning') as warning:
                self.assertFalse(rar_external.RarArchive.is_available())
                warning.assert_not_called()

    def test_free_handler_rejects_old_or_nonfree_versions(self):
        for version, expected in [(b'unrar-free 0.3.1', True),
                                  (b'unrar-free 0.1.3', False),
                                  (b'UNRAR 7.0', False)]:
            with self.subTest(version=version), \
                    mock.patch.object(unrar_free, '_unrar_free_executable', -1), \
                    mock.patch.object(unrar_free.subprocess, 'run') as run, \
                    mock.patch.object(unrar_free.process, 'find_executable') as find:
                run.return_value = subprocess.CompletedProcess([], 0, version, b'')
                find.side_effect = lambda candidates, is_valid_candidate: (
                    '/unrar' if is_valid_candidate('/unrar') else None)
                self.assertEqual(UnrarFreeArchive.is_available(), expected)


@unittest.skipUnless(UnrarFreeArchive.is_available(), 'requires unrar-free >= 0.3.0')
class UnrarFreeRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.out = self.root / 'out'

    def archive(self, name):
        return UnrarFreeArchive(fixture(name, self.root))

    def test_rar4_directories_and_single_extraction(self):
        archive = self.archive('test_read_format_rar.rar')
        names = archive.list_contents()
        self.assertIn('test.txt', names)
        self.assertIn('testdir/test.txt', names)
        self.assertNotIn('testdir', names)
        self.assertEqual(archive.list_contents(), names)
        archive.extract('testdir/test.txt', str(self.out))
        self.assertEqual((self.out / 'testdir/test.txt').read_bytes(),
                         b'test text document\r\n')
        self.assertFalse((self.out / 'test.txt').exists())

    def test_rar5_compressed_contents(self):
        archive = self.archive('test_read_format_rar5_compressed.rar')
        names = archive.list_contents()
        self.assertTrue(names)
        self.assertEqual(set(archive.iter_extract(names, str(self.out))), set(names))
        self.assertTrue(all((self.out / name).stat().st_size == size
                            for name, size in archive._contents))

    def test_rar5_solid_subset_byte_for_byte(self):
        archive = self.archive('test_read_format_rar5_multiple_files_solid.rar')
        self.assertEqual(archive.list_contents(),
                         ['test1.bin', 'test2.bin', 'test3.bin', 'test4.bin'])
        self.assertTrue(archive.is_solid())
        self.assertEqual(list(archive.iter_extract(['test2.bin', 'test4.bin'],
                                                 str(self.out))),
                         ['test2.bin', 'test4.bin'])
        for magic in (2, 4):
            expected = b''.join(struct.pack('<I', max(0, k*k - 3*k + 1 + magic))
                                for k in range(1, 1025))
            self.assertEqual((self.out / ('test%d.bin' % magic)).read_bytes(), expected)
        self.assertFalse((self.out / 'test1.bin').exists())

    def test_unicode_names(self):
        archive = self.archive('test_read_format_rar5_unicode.rar')
        names = archive.list_contents()
        self.assertTrue(any(not name.isascii() for name in names))
        self.assertEqual(list(archive.iter_extract(names, str(self.out))), names)

    def test_names_spaces_empty_files_and_no_directory_side_effects(self):
        archive = UnrarFreeArchive(stored_rar(self.root / 'names.rar', [
            ('sub/', b''), ('sub/ page [1]*.jpg ', b'image data'),
            ('-page.jpg', b'dash'), ('empty.txt', b'')]))
        with mock.patch.dict(os.environ, {'LC_ALL': 'C'}):
            self.assertEqual(archive.list_contents(),
                             ['sub/ page [1]*.jpg ', '-page.jpg', 'empty.txt'])
        # A print pass must never create archive directories in its cwd.
        with mock.patch.object(unrar_free, 'subprocess', wraps=subprocess) as child:
            child.PIPE = subprocess.PIPE
            child.Popen.side_effect = lambda *a, **kw: subprocess.Popen(
                *a, cwd=self.root, **kw)
            names = archive.list_contents()
            self.assertEqual(list(archive.iter_extract(names, str(self.out))), names)
        self.assertFalse((self.root / 'sub').exists())
        self.assertEqual((self.out / 'sub/ page [1]*.jpg ').read_bytes(), b'image data')
        self.assertEqual((self.out / 'empty.txt').read_bytes(), b'')

    def test_conflicting_sanitized_names_are_rejected(self):
        archive = UnrarFreeArchive(stored_rar(self.root / 'collision.rar',
                                            [('/page.jpg', b'a'), ('page.jpg', b'b')]))
        with self.assertRaisesRegex(OSError, 'conflicting member names'):
            archive.list_contents()

    def test_symlink_stream_size_mismatch_is_rejected(self):
        archive = self.archive('test_read_format_rar.rar')
        archive.list_contents()
        with self.assertRaisesRegex(OSError, 'trailing member data'):
            archive.extract('testlink', str(self.out))
        self.assertEqual(list(self.out.iterdir()), [])

    def test_large_selection_is_split_into_bounded_batches(self):
        members = [('page%04d%s.jpg' % (i, 'x' * 100), bytes([i % 256]))
                   for i in range(310)]
        archive = UnrarFreeArchive(stored_rar(self.root / 'many.rar', members))
        names = archive.list_contents()
        with mock.patch.object(subprocess, 'Popen', wraps=subprocess.Popen) as popen:
            self.assertEqual(list(archive.iter_extract(names, str(self.out))), names)
            self.assertEqual(popen.call_count, 2)
        for name, content in members:
            self.assertEqual((self.out / name).read_bytes(), content)

    def test_newline_names_are_rejected(self):
        archive = UnrarFreeArchive(stored_rar(self.root / 'newline.rar',
                                            [('page\n.jpg', b'a')]))
        with self.assertRaisesRegex(OSError, 'ambiguous member name'):
            archive.list_contents()

    def test_encrypted_headers_report_capability_limit(self):
        archive = self.archive('test_read_format_rar_encryption_header.rar')
        with self.assertRaisesRegex(OSError, 'encryption|Encrypted'):
            archive.list_contents()
        self.assertFalse(archive.filenames_initialized)

    def test_encrypted_data_never_publishes_empty_image(self):
        archive = self.archive('test_read_format_rar_encryption_data.rar')
        names = archive.list_contents()
        with self.assertRaises(OSError):
            list(archive.iter_extract(names, str(self.out)))
        self.assertEqual(list(self.out.rglob('*')), [])

    def test_truncated_stream_preserves_existing_file_and_cleans_temps(self):
        path = self.root / 'truncated.rar'
        archive = UnrarFreeArchive(stored_rar(path, [('page.jpg', b'image data')]))
        archive.list_contents()
        self.out.mkdir()
        (self.out / 'page.jpg').write_bytes(b'existing image')
        path.write_bytes(path.read_bytes()[:-20])
        with self.assertRaises(OSError):
            archive.extract('page.jpg', str(self.out))
        self.assertEqual((self.out / 'page.jpg').read_bytes(), b'existing image')
        self.assertEqual(list(self.out.iterdir()), [self.out / 'page.jpg'])

    def test_nonzero_exit_even_with_complete_data_is_rejected(self):
        archive = UnrarFreeArchive(stored_rar(self.root / 'status.rar',
                                            [('page.jpg', b'image data')]))
        archive.list_contents()
        # A backend can emit the advertised size and still fail its CRC check.
        class FailedStatus(subprocess.Popen):
            def wait(self, *args, **kwargs):
                super().wait(*args, **kwargs)
                return 1

        with mock.patch.object(subprocess, 'Popen', FailedStatus):
            with self.assertRaisesRegex(OSError, 'extraction failed'):
                archive.extract('page.jpg', str(self.out))
        self.assertEqual(list(self.out.iterdir()), [])

    def test_unsupported_rar4_solid_is_not_reported_as_empty(self):
        archive = UnrarFreeArchive(stored_rar(self.root / 'solid.rar',
                                            [('page1.jpg', b'a'), ('page2.jpg', b'b')],
                                            solid=True))
        with self.assertRaisesRegex(OSError, 'solid'):
            archive.list_contents()


if __name__ == '__main__':
    unittest.main()
