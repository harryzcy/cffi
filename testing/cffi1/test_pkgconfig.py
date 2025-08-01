import sys
import subprocess
import pytest
import cffi.pkgconfig as pkgconfig
from cffi import PkgConfigError


def mock_call(libname, flag):
    assert libname=="foobarbaz"
    flags = {
        "--cflags": "-I/usr/include/python3.6m -DABCD -DCFFI_TEST=1 -O42\n",
        "--libs": "-L/usr/lib64 -lpython3.6 -shared\n",
    }
    return flags[flag]


def test_merge_flags():
    d1 = {"ham": [1, 2, 3], "spam" : ["a", "b", "c"], "foo" : []}
    d2 = {"spam" : ["spam", "spam", "spam"], "bar" : ["b", "a", "z"]}

    pkgconfig.merge_flags(d1, d2)
    assert d1 == {
        "ham": [1, 2, 3],
        "spam" : ["a", "b", "c", "spam", "spam", "spam"],
        "bar" : ["b", "a", "z"],
        "foo" : []}


@pytest.mark.thread_unsafe(reason="monkeypatches pkgconfig")
def test_pkgconfig():
    assert pkgconfig.flags_from_pkgconfig([]) == {}

    saved = pkgconfig.call
    try:
        pkgconfig.call = mock_call
        flags = pkgconfig.flags_from_pkgconfig(["foobarbaz"])
    finally:
        pkgconfig.call = saved
    assert flags == {
        'include_dirs': ['/usr/include/python3.6m'],
        'library_dirs': ['/usr/lib64'],
        'libraries': ['python3.6'],
        'define_macros': [('ABCD', None), ('CFFI_TEST', '1')],
        'extra_compile_args': ['-O42'],
        'extra_link_args': ['-shared']
    }

class mock_subprocess:
    PIPE = Ellipsis
    class Popen:
        def __init__(self, cmd, stdout, stderr):
            if mock_subprocess.RESULT is None:
                raise OSError("oops can't run")
            assert cmd == ['pkg-config', '--print-errors', '--cflags', 'libfoo']
        def communicate(self):
            bout, berr, rc = mock_subprocess.RESULT
            self.returncode = rc
            return bout, berr

@pytest.mark.thread_unsafe(reason="monkeypatches pkgconfig")
def test_call():
    saved = pkgconfig.subprocess
    try:
        pkgconfig.subprocess = mock_subprocess

        mock_subprocess.RESULT = None
        e = pytest.raises(PkgConfigError, pkgconfig.call, "libfoo", "--cflags")
        assert str(e.value) == "cannot run pkg-config: oops can't run"

        mock_subprocess.RESULT = b"", "Foo error!\n", 1
        e = pytest.raises(PkgConfigError, pkgconfig.call, "libfoo", "--cflags")
        assert str(e.value) == "Foo error!"

        mock_subprocess.RESULT = b"abc\\def\n", "", 0
        e = pytest.raises(PkgConfigError, pkgconfig.call, "libfoo", "--cflags")
        assert str(e.value).startswith("pkg-config --cflags libfoo returned an "
                                       "unsupported backslash-escaped output:")

        mock_subprocess.RESULT = b"abc def\n", "", 0
        result = pkgconfig.call("libfoo", "--cflags")
        assert result == "abc def\n"

        mock_subprocess.RESULT = b"abc def\n", "", 0
        result = pkgconfig.call("libfoo", "--cflags")
        assert result == "abc def\n"

        if sys.version_info >= (3,):
            mock_subprocess.RESULT = b"\xff\n", "", 0
            e = pytest.raises(PkgConfigError, pkgconfig.call,
                               "libfoo", "--cflags", encoding="utf-8")
            assert str(e.value) == (
                "pkg-config --cflags libfoo returned bytes that cannot be "
                "decoded with encoding 'utf-8':\nb'\\xff\\n'")

    finally:
        pkgconfig.subprocess = saved
