"""RAR fallback for the libarchive-based unrar-free (0.3.0 or newer).

Its human-readable listing has neither solid nor encryption flags. Always
use a sequential pass, and check the process status before publishing files.
RAR encryption and RAR4 solid archives need one of the preferred handlers.
"""

import os
import re
import subprocess
import tempfile

from mcomix import process
from mcomix.archive import archive_base


_unrar_free_executable = -1


class UnrarFreeArchive(archive_base.ExternalExecutableArchive):
    support_concurrent_extractions = False

    _separator = b'-' * 46
    _metadata = re.compile(
        rb' {12}\s*(\d+) \d{2}-\d{2}-\d{2} \d{2}:\d{2}   ([.A-Z]{6})')
    _summary = re.compile(rb'\s*(\d+)\s+(\d+)\s*')

    def __init__(self, archive):
        super().__init__(archive)
        self._contents = []

    @staticmethod
    def _find_executable():
        global _unrar_free_executable
        if _unrar_free_executable == -1:
            def supported(exe):
                try:
                    result = subprocess.run(
                        [exe, '--version'], stdin=process.NULL,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=5, creationflags=process._get_creationflags())
                except (OSError, subprocess.TimeoutExpired):
                    return False
                version = re.search(rb'\bunrar-free (\d+)\.(\d+)\.(\d+)',
                                    result.stdout)
                return (result.returncode == 0 and version is not None
                        and tuple(map(int, version.groups())) >= (0, 3, 0))

            _unrar_free_executable = process.find_executable(
                ('unrar-free', 'unrar'), is_valid_candidate=supported)
        return _unrar_free_executable

    @staticmethod
    def is_available():
        return bool(UnrarFreeArchive._find_executable())

    def _get_executable(self):
        return self._find_executable()

    def is_solid(self):
        # The listing cannot distinguish solid archives; avoid repeated scans.
        return True

    def _arguments(self, command):
        # -ep also prevents unrar-free's print command from creating directory
        # entries in the working directory. -p- prevents terminal prompting.
        args = [self._get_executable(), command, '-p-', '-ep']
        if command == 'p':
            args.append('-inul')
        return args + ['--', os.path.abspath(self.archive)]

    @staticmethod
    def _environment():
        env = os.environ.copy()
        env['LC_ALL'] = 'C.UTF-8'
        return env

    def _error(self, detail):
        return OSError(
            'unrar-free could not read %s: %s. Encrypted RAR and RAR4 solid '
            'archives require unrar/libunrar or a RAR-capable 7z.'
            % (self.archive, detail))

    def _parse_listing(self, output):
        # Parse complete name/metadata pairs, preserving leading/trailing spaces.
        # A newline in a name makes this format ambiguous: fail rather than
        # extracting the wrong member. Also validate the footer count/size.
        lines = output.split(b'\n')
        try:
            start = lines.index(b'Pathname/Comment')
            start = lines.index(self._separator, start) + 1
        except ValueError:
            raise self._error('unrecognized listing format')
        entries = []
        count = total = 0
        while start < len(lines) and lines[start] != self._separator:
            if start + 1 >= len(lines) or not lines[start].startswith(b' '):
                raise self._error('ambiguous member name in listing')
            metadata = self._metadata.fullmatch(lines[start + 1])
            if metadata is None:
                raise self._error('ambiguous member name or metadata in listing')
            size = int(metadata[1])
            count += 1
            total += size
            if b'D' not in metadata[2]:
                try:
                    name = lines[start][1:].decode('utf-8')
                except UnicodeDecodeError:
                    raise self._error('member name is not UTF-8')
                entries.append((name, size))
            start += 2
        if start + 1 >= len(lines):
            raise self._error('incomplete listing')
        summary = self._summary.fullmatch(lines[start + 1])
        if summary is None or tuple(map(int, summary.groups())) != (count, total):
            raise self._error('incomplete listing')
        return entries

    def iter_contents(self):
        if self.filenames_initialized:
            yield from (name for name, _ in self._contents)
            return
        if not self._get_executable():
            raise self._error('no supported executable found')
        result = subprocess.run(
            self._arguments('l'), stdin=process.NULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=self._environment(),
            creationflags=process._get_creationflags())
        if result.returncode:
            raise self._error(result.stderr.decode('utf-8', 'replace').strip()
                              or 'listing failed')
        entries = self._parse_listing(result.stdout)
        contents = []
        mapping = {}
        for original, size in entries:
            safe = self._replace_invalid_filesystem_chars(original)
            if not safe or safe in mapping:
                raise self._error('empty or conflicting member names')
            # unrar-free normalizes backslashes before comparing member names.
            mapping[safe] = original.replace('\\', '/')
            contents.append((safe, size))
        self.unicode_mapping = mapping
        self._contents = contents
        self.filenames_initialized = True
        yield from (name for name, _ in contents)

    def extract(self, filename, destination_dir):
        # Use the same checked extraction path for individual members.
        for _ in self.iter_extract([filename], destination_dir):
            pass

    def iter_extract(self, entries, destination_dir):
        if not self.filenames_initialized:
            self.list_contents()
        wanted = set(entries)
        known = {name for name, _ in self._contents}
        if not wanted <= known:
            raise self._error('requested member is not in the listing')
        if not wanted:
            return
        # unrar-free compares names literally, without wildcard expansion.
        # Restrict stdout to selected members: symlinks can produce bytes even
        # though the listing advertises size zero. Bound argv for large comics.
        batches = []
        batch = []
        argument_size = 0
        for name, size in self._contents:
            if name not in wanted:
                continue
            cost = len(self._original_filename(name).encode('utf-8')) + 1
            if batch and argument_size + cost > 32768:
                batches.append(batch)
                batch = []
                argument_size = 0
            batch.append((name, size))
            argument_size += cost
        batches.append(batch)
        staged = []
        try:
            for batch in batches:
                args = self._arguments('p') + [self._original_filename(name)
                                               for name, _ in batch]
                # A full stderr pipe must not block stdout.
                with tempfile.TemporaryFile() as errors:
                    proc = subprocess.Popen(
                        args, stdin=process.NULL, stdout=subprocess.PIPE,
                        stderr=errors, env=self._environment(),
                        creationflags=process._get_creationflags())
                    try:
                        for name, size in batch:
                            target = os.path.join(destination_dir, name)
                            self._create_directory(os.path.dirname(target))
                            with tempfile.NamedTemporaryFile(
                                    dir=os.path.dirname(target),
                                    prefix='.mcomix-unrar-', delete=False) as output:
                                staged.append((name, output.name, target))
                                remaining = size
                                while remaining:
                                    data = proc.stdout.read(min(remaining, 65536))
                                    if not data:
                                        raise self._error('truncated member data')
                                    remaining -= len(data)
                                    output.write(data)
                        if proc.stdout.read(1):
                            raise self._error('unexpected trailing member data')
                        if proc.wait():
                            errors.seek(0)
                            raise self._error(
                                errors.read().decode('utf-8', 'replace').strip()
                                or 'extraction failed')
                    finally:
                        proc.stdout.close()
                        if proc.poll() is None:
                            proc.kill()
                        proc.wait()
            # Publish only once every batch has passed length and status checks.
            for name, temporary, target in staged:
                os.replace(temporary, target)
                yield name
        finally:
            for _, temporary, _ in staged:
                if os.path.exists(temporary):
                    os.unlink(temporary)
