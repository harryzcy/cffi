import pytest
import platform
import sys, ctypes, ctypes.util
from cffi import FFI, CDefError, FFIError, VerificationMissing
from testing.support import *

SIZE_OF_INT   = ctypes.sizeof(ctypes.c_int)
SIZE_OF_LONG  = ctypes.sizeof(ctypes.c_long)
SIZE_OF_SHORT = ctypes.sizeof(ctypes.c_short)
SIZE_OF_PTR   = ctypes.sizeof(ctypes.c_void_p)
SIZE_OF_WCHAR = ctypes.sizeof(ctypes.c_wchar)

def needs_dlopen_none():
    if sys.platform == 'win32' and not ctypes.util.find_library('c'):
        pytest.skip("dlopen(None) cannot work on Windows with this runtime")


class BackendTests:

    def test_integer_ranges(self):
        ffi = FFI(backend=self.Backend())
        for (c_type, size) in [('char', 1),
                               ('short', 2),
                               ('short int', 2),
                               ('', 4),
                               ('int', 4),
                               ('long', SIZE_OF_LONG),
                               ('long int', SIZE_OF_LONG),
                               ('long long', 8),
                               ('long long int', 8),
                               ]:
            for unsigned in [None, False, True]:
                c_decl = {None: '',
                          False: 'signed ',
                          True: 'unsigned '}[unsigned] + c_type
                if c_decl == 'char' or c_decl == '':
                    continue
                self._test_int_type(ffi, c_decl, size, unsigned)

    def test_fixedsize_int(self):
        ffi = FFI(backend=self.Backend())
        for size in [1, 2, 4, 8]:
            self._test_int_type(ffi, 'int%d_t' % (8*size), size, False)
            self._test_int_type(ffi, 'uint%d_t' % (8*size), size, True)
        self._test_int_type(ffi, 'intptr_t', SIZE_OF_PTR, False)
        self._test_int_type(ffi, 'uintptr_t', SIZE_OF_PTR, True)
        self._test_int_type(ffi, 'ptrdiff_t', SIZE_OF_PTR, False)
        self._test_int_type(ffi, 'size_t', SIZE_OF_PTR, True)
        self._test_int_type(ffi, 'ssize_t', SIZE_OF_PTR, False)

    def _test_int_type(self, ffi, c_decl, size, unsigned):
        if unsigned:
            min = 0
            max = (1 << (8*size)) - 1
        else:
            min = -(1 << (8*size-1))
            max = (1 << (8*size-1)) - 1
        min = int(min)
        max = int(max)
        p = ffi.cast(c_decl, min)
        assert p == min
        assert hash(p) == hash(min)
        assert bool(p) is bool(min)
        assert int(p) == min
        p = ffi.cast(c_decl, max)
        assert int(p) == max
        p = ffi.cast(c_decl, long(max))
        assert int(p) == max
        q = ffi.cast(c_decl, min - 1)
        assert ffi.typeof(q) is ffi.typeof(p) and int(q) == max
        q = ffi.cast(c_decl, long(min - 1))
        assert ffi.typeof(q) is ffi.typeof(p) and int(q) == max
        assert q == p
        assert int(q) == int(p)
        assert hash(q) == hash(p)
        c_decl_ptr = '%s *' % c_decl
        pytest.raises(OverflowError, ffi.new, c_decl_ptr, min - 1)
        pytest.raises(OverflowError, ffi.new, c_decl_ptr, max + 1)
        pytest.raises(OverflowError, ffi.new, c_decl_ptr, long(min - 1))
        pytest.raises(OverflowError, ffi.new, c_decl_ptr, long(max + 1))
        assert ffi.new(c_decl_ptr, min)[0] == min
        assert ffi.new(c_decl_ptr, max)[0] == max
        assert ffi.new(c_decl_ptr, long(min))[0] == min
        assert ffi.new(c_decl_ptr, long(max))[0] == max

    def test_new_unsupported_type(self):
        ffi = FFI(backend=self.Backend())
        e = pytest.raises(TypeError, ffi.new, "int")
        assert str(e.value) == "expected a pointer or array ctype, got 'int'"

    def test_new_single_integer(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int *")     # similar to ffi.new("int[1]")
        assert p[0] == 0
        p[0] = -123
        assert p[0] == -123
        p = ffi.new("int *", -42)
        assert p[0] == -42
        assert repr(p) == "<cdata 'int *' owning %d bytes>" % SIZE_OF_INT

    def test_new_array_no_arg(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[10]")
        # the object was zero-initialized:
        for i in range(10):
            assert p[i] == 0

    def test_array_indexing(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[10]")
        p[0] = 42
        p[9] = 43
        assert p[0] == 42
        assert p[9] == 43
        with pytest.raises(IndexError):
            p[10]
        with pytest.raises(IndexError):
            p[10] = 44
        with pytest.raises(IndexError):
            p[-1]
        with pytest.raises(IndexError):
            p[-1] = 44

    def test_array_slicing(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[10]")
        for i in range(10):
            p[i] = i
        assert repr(p[0:3]) == "<cdata 'int[]' sliced length 3>"
        assert list(p[0:3]) == [0, 1, 2]
        with pytest.raises(IndexError):
            _ = p[0:11]

    def test_new_array_args(self):
        ffi = FFI(backend=self.Backend())
        # this tries to be closer to C: where we say "int x[5] = {10, 20, ..}"
        # then here we must enclose the items in a list
        p = ffi.new("int[5]", [10, 20, 30, 40, 50])
        assert p[0] == 10
        assert p[1] == 20
        assert p[2] == 30
        assert p[3] == 40
        assert p[4] == 50
        p = ffi.new("int[4]", [25])
        assert p[0] == 25
        assert p[1] == 0     # follow C convention rather than LuaJIT's
        assert p[2] == 0
        assert p[3] == 0
        p = ffi.new("int[4]", [ffi.cast("int", -5)])
        assert p[0] == -5
        assert repr(p) == "<cdata 'int[4]' owning %d bytes>" % (4*SIZE_OF_INT)

    def test_new_array_varsize(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[]", 10)     # a single integer is the length
        assert p[9] == 0
        with pytest.raises(IndexError):
            p[10]
        #
        pytest.raises(TypeError, ffi.new, "int[]")
        #
        p = ffi.new("int[]", [-6, -7])    # a list is all the items, like C
        assert p[0] == -6
        assert p[1] == -7
        with pytest.raises(IndexError):
            p[2]
        assert repr(p) == "<cdata 'int[]' owning %d bytes>" % (2*SIZE_OF_INT)
        #
        p = ffi.new("int[]", 0)
        with pytest.raises(IndexError):
            p[0]
        pytest.raises(ValueError, ffi.new, "int[]", -1)
        assert repr(p) == "<cdata 'int[]' owning 0 bytes>"

    def test_pointer_init(self):
        ffi = FFI(backend=self.Backend())
        n = ffi.new("int *", 24)
        a = ffi.new("int *[10]", [ffi.NULL, ffi.NULL, n, n, ffi.NULL])
        for i in range(10):
            if i not in (2, 3):
                assert a[i] == ffi.NULL
        assert a[2] == a[3] == n

    def test_cannot_cast(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short int[10]")
        e = pytest.raises(TypeError, ffi.new, "long int **", a)
        msg = str(e.value)
        assert "'short[10]'" in msg and "'long *'" in msg

    def test_new_pointer_to_array(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("int[4]", [100, 102, 104, 106])
        p = ffi.new("int **", a)
        assert p[0] == ffi.cast("int *", a)
        assert p[0][2] == 104
        p = ffi.cast("int *", a)
        assert p[0] == 100
        assert p[1] == 102
        assert p[2] == 104
        assert p[3] == 106
        # keepalive: a

    def test_pointer_direct(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.cast("int*", 0)
        assert p is not None
        assert bool(p) is False
        assert p == ffi.cast("int*", 0)
        assert p != None
        assert repr(p) == "<cdata 'int *' NULL>"
        a = ffi.new("int[]", [123, 456])
        p = ffi.cast("int*", a)
        assert bool(p) is True
        assert p == ffi.cast("int*", a)
        assert p != ffi.cast("int*", 0)
        assert p[0] == 123
        assert p[1] == 456

    def test_repr(self):
        typerepr = self.TypeRepr
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { short a, b, c; };")
        p = ffi.cast("short unsigned int", 0)
        assert repr(p) == "<cdata 'unsigned short' 0>"
        assert repr(ffi.typeof(p)) == typerepr % "unsigned short"
        p = ffi.cast("unsigned short int", 0)
        assert repr(p) == "<cdata 'unsigned short' 0>"
        assert repr(ffi.typeof(p)) == typerepr % "unsigned short"
        p = ffi.cast("int*", 0)
        assert repr(p) == "<cdata 'int *' NULL>"
        assert repr(ffi.typeof(p)) == typerepr % "int *"
        #
        p = ffi.new("int*")
        assert repr(p) == "<cdata 'int *' owning %d bytes>" % SIZE_OF_INT
        assert repr(ffi.typeof(p)) == typerepr % "int *"
        p = ffi.new("int**")
        assert repr(p) == "<cdata 'int * *' owning %d bytes>" % SIZE_OF_PTR
        assert repr(ffi.typeof(p)) == typerepr % "int * *"
        p = ffi.new("int [2]")
        assert repr(p) == "<cdata 'int[2]' owning %d bytes>" % (2*SIZE_OF_INT)
        assert repr(ffi.typeof(p)) == typerepr % "int[2]"
        p = ffi.new("int*[2][3]")
        assert repr(p) == "<cdata 'int *[2][3]' owning %d bytes>" % (
            6*SIZE_OF_PTR)
        assert repr(ffi.typeof(p)) == typerepr % "int *[2][3]"
        p = ffi.new("struct foo *")
        assert repr(p) == "<cdata 'struct foo *' owning %d bytes>" % (
            3*SIZE_OF_SHORT)
        assert repr(ffi.typeof(p)) == typerepr % "struct foo *"
        #
        q = ffi.cast("short", -123)
        assert repr(q) == "<cdata 'short' -123>"
        assert repr(ffi.typeof(q)) == typerepr % "short"
        p = ffi.new("int*")
        q = ffi.cast("short*", p)
        assert repr(q).startswith("<cdata 'short *' 0x")
        assert repr(ffi.typeof(q)) == typerepr % "short *"
        p = ffi.new("int [2]")
        q = ffi.cast("int*", p)
        assert repr(q).startswith("<cdata 'int *' 0x")
        assert repr(ffi.typeof(q)) == typerepr % "int *"
        p = ffi.new("struct foo*")
        q = ffi.cast("struct foo *", p)
        assert repr(q).startswith("<cdata 'struct foo *' 0x")
        assert repr(ffi.typeof(q)) == typerepr % "struct foo *"
        prevrepr = repr(q)
        q = q[0]
        assert repr(q) == prevrepr.replace(' *', ' &')
        assert repr(ffi.typeof(q)) == typerepr % "struct foo"

    def test_new_array_of_array(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[3][4]")
        p[0][0] = 10
        p[2][3] = 33
        assert p[0][0] == 10
        assert p[2][3] == 33
        with pytest.raises(IndexError):
            p[1][-1]

    def test_constructor_array_of_array(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[3][2]", [[10, 11], [12, 13], [14, 15]])
        assert p[2][1] == 15

    def test_new_array_of_pointer_1(self):
        ffi = FFI(backend=self.Backend())
        n = ffi.new("int*", 99)
        p = ffi.new("int*[4]")
        p[3] = n
        a = p[3]
        assert repr(a).startswith("<cdata 'int *' 0x")
        assert a[0] == 99

    def test_new_array_of_pointer_2(self):
        ffi = FFI(backend=self.Backend())
        n = ffi.new("int[1]", [99])
        p = ffi.new("int*[4]")
        p[3] = n
        a = p[3]
        assert repr(a).startswith("<cdata 'int *' 0x")
        assert a[0] == 99

    def test_char(self):
        ffi = FFI(backend=self.Backend())
        assert ffi.new("char*", b"\xff")[0] == b'\xff'
        assert ffi.new("char*")[0] == b'\x00'
        assert int(ffi.cast("char", 300)) == 300 - 256
        assert not bool(ffi.cast("char", 0))
        assert bool(ffi.cast("char", 1))
        assert bool(ffi.cast("char", 255))
        pytest.raises(TypeError, ffi.new, "char*", 32)
        pytest.raises(TypeError, ffi.new, "char*", u+"x")
        pytest.raises(TypeError, ffi.new, "char*", b"foo")
        #
        p = ffi.new("char[]", [b'a', b'b', b'\x9c'])
        assert len(p) == 3
        assert p[0] == b'a'
        assert p[1] == b'b'
        assert p[2] == b'\x9c'
        p[0] = b'\xff'
        assert p[0] == b'\xff'
        p = ffi.new("char[]", b"abcd")
        assert len(p) == 5
        assert p[4] == b'\x00'    # like in C, with:  char[] p = "abcd";
        #
        p = ffi.new("char[4]", b"ab")
        assert len(p) == 4
        assert [p[i] for i in range(4)] == [b'a', b'b', b'\x00', b'\x00']
        p = ffi.new("char[2]", b"ab")
        assert len(p) == 2
        assert [p[i] for i in range(2)] == [b'a', b'b']
        pytest.raises(IndexError, ffi.new, "char[2]", b"abc")

    def check_wchar_t(self, ffi):
        try:
            ffi.cast("wchar_t", 0)
        except NotImplementedError:
            pytest.skip("NotImplementedError: wchar_t")

    def test_wchar_t(self):
        ffi = FFI(backend=self.Backend())
        self.check_wchar_t(ffi)
        assert ffi.new("wchar_t*", u+'x')[0] == u+'x'
        assert ffi.new("wchar_t*", u+'\u1234')[0] == u+'\u1234'
        if SIZE_OF_WCHAR > 2:
            assert ffi.new("wchar_t*", u+'\U00012345')[0] == u+'\U00012345'
        else:
            pytest.raises(TypeError, ffi.new, "wchar_t*", u+'\U00012345')
        assert ffi.new("wchar_t*")[0] == u+'\x00'
        assert int(ffi.cast("wchar_t", 300)) == 300
        assert not bool(ffi.cast("wchar_t", 0))
        assert bool(ffi.cast("wchar_t", 1))
        assert bool(ffi.cast("wchar_t", 65535))
        if SIZE_OF_WCHAR > 2:
            assert bool(ffi.cast("wchar_t", 65536))
        pytest.raises(TypeError, ffi.new, "wchar_t*", 32)
        pytest.raises(TypeError, ffi.new, "wchar_t*", "foo")
        #
        p = ffi.new("wchar_t[]", [u+'a', u+'b', u+'\u1234'])
        assert len(p) == 3
        assert p[0] == u+'a'
        assert p[1] == u+'b' and type(p[1]) is unicode
        assert p[2] == u+'\u1234'
        p[0] = u+'x'
        assert p[0] == u+'x' and type(p[0]) is unicode
        p[1] = u+'\u1357'
        assert p[1] == u+'\u1357'
        p = ffi.new("wchar_t[]", u+"abcd")
        assert len(p) == 5
        assert p[4] == u+'\x00'
        p = ffi.new("wchar_t[]", u+"a\u1234b")
        assert len(p) == 4
        assert p[1] == u+'\u1234'
        #
        p = ffi.new("wchar_t[]", u+'\U00023456')
        if SIZE_OF_WCHAR == 2:
            assert len(p) == 3
            assert p[0] == u+'\ud84d'
            assert p[1] == u+'\udc56'
            assert p[2] == u+'\x00'
        else:
            assert len(p) == 2
            assert p[0] == u+'\U00023456'
            assert p[1] == u+'\x00'
        #
        p = ffi.new("wchar_t[4]", u+"ab")
        assert len(p) == 4
        assert [p[i] for i in range(4)] == [u+'a', u+'b', u+'\x00', u+'\x00']
        p = ffi.new("wchar_t[2]", u+"ab")
        assert len(p) == 2
        assert [p[i] for i in range(2)] == [u+'a', u+'b']
        pytest.raises(IndexError, ffi.new, "wchar_t[2]", u+"abc")

    def test_none_as_null_doesnt_work(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int*[1]")
        assert p[0] is not None
        assert p[0] != None
        assert p[0] == ffi.NULL
        assert repr(p[0]) == "<cdata 'int *' NULL>"
        #
        n = ffi.new("int*", 99)
        p = ffi.new("int*[]", [n])
        assert p[0][0] == 99
        with pytest.raises(TypeError):
            p[0] = None
        p[0] = ffi.NULL
        assert p[0] == ffi.NULL

    def test_float(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("float[]", [-2, -2.5])
        assert p[0] == -2.0
        assert p[1] == -2.5
        p[1] += 17.75
        assert p[1] == 15.25
        #
        p = ffi.new("float*", 15.75)
        assert p[0] == 15.75
        pytest.raises(TypeError, int, p)
        pytest.raises(TypeError, float, p)
        p[0] = 0.0
        assert bool(p) is True
        #
        p = ffi.new("float*", 1.1)
        f = p[0]
        assert f != 1.1      # because of rounding effect
        assert abs(f - 1.1) < 1E-7
        #
        INF = 1E200 * 1E200
        assert 1E200 != INF
        p[0] = 1E200
        assert p[0] == INF     # infinite, not enough precision

    def test_struct_simple(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a; short b, c; };")
        s = ffi.new("struct foo*")
        assert s.a == s.b == s.c == 0
        s.b = -23
        assert s.b == -23
        with pytest.raises(OverflowError):
            s.b = 32768
        #
        s = ffi.new("struct foo*", [-2, -3])
        assert s.a == -2
        assert s.b == -3
        assert s.c == 0
        with pytest.raises((AttributeError, TypeError)):
            del s.a
        assert repr(s) == "<cdata 'struct foo *' owning %d bytes>" % (
            SIZE_OF_INT + 2 * SIZE_OF_SHORT)
        #
        pytest.raises(ValueError, ffi.new, "struct foo*", [1, 2, 3, 4])

    def test_constructor_struct_from_dict(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a; short b, c; };")
        s = ffi.new("struct foo*", {'b': 123, 'c': 456})
        assert s.a == 0
        assert s.b == 123
        assert s.c == 456
        pytest.raises(KeyError, ffi.new, "struct foo*", {'d': 456})

    def test_struct_pointer(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a; short b, c; };")
        s = ffi.new("struct foo*")
        assert s[0].a == s[0].b == s[0].c == 0
        s[0].b = -23
        assert s[0].b == s.b == -23
        with pytest.raises(OverflowError):
            s[0].b = -32769
        with pytest.raises(IndexError):
            s[1]

    def test_struct_opaque(self):
        ffi = FFI(backend=self.Backend())
        pytest.raises(TypeError, ffi.new, "struct baz*")
        p = ffi.new("struct baz **")    # this works
        assert p[0] == ffi.NULL

    def test_pointer_to_struct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a; short b, c; };")
        s = ffi.new("struct foo *")
        s.a = -42
        assert s[0].a == -42
        p = ffi.new("struct foo **", s)
        assert p[0].a == -42
        assert p[0][0].a == -42
        p[0].a = -43
        assert s.a == -43
        assert s[0].a == -43
        p[0][0].a = -44
        assert s.a == -44
        assert s[0].a == -44
        s.a = -45
        assert p[0].a == -45
        assert p[0][0].a == -45
        s[0].a = -46
        assert p[0].a == -46
        assert p[0][0].a == -46

    def test_constructor_struct_of_array(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a[2]; char b[3]; };")
        s = ffi.new("struct foo *", [[10, 11], [b'a', b'b', b'c']])
        assert s.a[1] == 11
        assert s.b[2] == b'c'
        s.b[1] = b'X'
        assert s.b[0] == b'a'
        assert s.b[1] == b'X'
        assert s.b[2] == b'c'

    def test_recursive_struct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int value; struct foo *next; };")
        s = ffi.new("struct foo*")
        t = ffi.new("struct foo*")
        s.value = 123
        s.next = t
        t.value = 456
        assert s.value == 123
        assert s.next.value == 456

    def test_union_simple(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("union foo { int a; short b, c; };")
        u = ffi.new("union foo*")
        assert u.a == u.b == u.c == 0
        u.b = -23
        assert u.b == -23
        assert u.a != 0
        with pytest.raises(OverflowError):
            u.b = 32768
        #
        u = ffi.new("union foo*", [-2])
        assert u.a == -2
        with pytest.raises((AttributeError, TypeError)):
            del u.a
        assert repr(u) == "<cdata 'union foo *' owning %d bytes>" % SIZE_OF_INT

    def test_union_opaque(self):
        ffi = FFI(backend=self.Backend())
        pytest.raises(TypeError, ffi.new, "union baz *")
        u = ffi.new("union baz **")   # this works
        assert u[0] == ffi.NULL

    def test_union_initializer(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("union foo { char a; int b; };")
        pytest.raises(TypeError, ffi.new, "union foo*", b'A')
        pytest.raises(TypeError, ffi.new, "union foo*", 5)
        pytest.raises(ValueError, ffi.new, "union foo*", [b'A', 5])
        u = ffi.new("union foo*", [b'A'])
        assert u.a == b'A'
        pytest.raises(TypeError, ffi.new, "union foo*", [1005])
        u = ffi.new("union foo*", {'b': 12345})
        assert u.b == 12345
        u = ffi.new("union foo*", [])
        assert u.a == b'\x00'
        assert u.b == 0

    def test_sizeof_type(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            struct foo { int a; short b, c, d; };
            union foo { int a; short b, c, d; };
        """)
        for c_type, expected_size in [
            ('char', 1),
            ('unsigned int', 4),
            ('char *', SIZE_OF_PTR),
            ('int[5]', 20),
            ('struct foo', 12),
            ('union foo', 4),
            ]:
            size = ffi.sizeof(c_type)
            assert size == expected_size, (size, expected_size, ctype)

    def test_sizeof_cdata(self):
        ffi = FFI(backend=self.Backend())
        assert ffi.sizeof(ffi.new("short*")) == SIZE_OF_PTR
        assert ffi.sizeof(ffi.cast("short", 123)) == SIZE_OF_SHORT
        #
        a = ffi.new("int[]", [10, 11, 12, 13, 14])
        assert len(a) == 5
        assert ffi.sizeof(a) == 5 * SIZE_OF_INT

    def test_string_from_char_pointer(self):
        ffi = FFI(backend=self.Backend())
        x = ffi.new("char*", b"x")
        assert str(x) == repr(x)
        assert ffi.string(x) == b"x"
        assert ffi.string(ffi.new("char*", b"\x00")) == b""
        pytest.raises(TypeError, ffi.new, "char*", unicode("foo"))

    def test_unicode_from_wchar_pointer(self):
        ffi = FFI(backend=self.Backend())
        self.check_wchar_t(ffi)
        x = ffi.new("wchar_t*", u+"x")
        assert unicode(x) == unicode(repr(x))
        assert ffi.string(x) == u+"x"
        assert ffi.string(ffi.new("wchar_t*", u+"\x00")) == u+""

    def test_string_from_char_array(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("char[]", b"hello.")
        p[5] = b'!'
        assert ffi.string(p) == b"hello!"
        p[6] = b'?'
        assert ffi.string(p) == b"hello!?"
        p[3] = b'\x00'
        assert ffi.string(p) == b"hel"
        assert ffi.string(p, 2) == b"he"
        with pytest.raises(IndexError):
            p[7] = b'X'
        #
        a = ffi.new("char[]", b"hello\x00world")
        assert len(a) == 12
        p = ffi.cast("char *", a)
        assert ffi.string(p) == b'hello'

    def test_string_from_wchar_array(self):
        ffi = FFI(backend=self.Backend())
        self.check_wchar_t(ffi)
        assert ffi.string(ffi.cast("wchar_t", "x")) == u+"x"
        assert ffi.string(ffi.cast("wchar_t", u+"x")) == u+"x"
        x = ffi.cast("wchar_t", "x")
        assert str(x) == repr(x)
        assert ffi.string(x) == u+"x"
        #
        p = ffi.new("wchar_t[]", u+"hello.")
        p[5] = u+'!'
        assert ffi.string(p) == u+"hello!"
        p[6] = u+'\u04d2'
        assert ffi.string(p) == u+"hello!\u04d2"
        p[3] = u+'\x00'
        assert ffi.string(p) == u+"hel"
        assert ffi.string(p, 123) == u+"hel"
        with pytest.raises(IndexError):
            p[7] = u+'X'
        #
        a = ffi.new("wchar_t[]", u+"hello\x00world")
        assert len(a) == 12
        p = ffi.cast("wchar_t *", a)
        assert ffi.string(p) == u+'hello'
        assert ffi.string(p, 123) == u+'hello'
        assert ffi.string(p, 5) == u+'hello'
        assert ffi.string(p, 2) == u+'he'

    def test_fetch_const_char_p_field(self):
        # 'const' is ignored so far
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { const char *name; };")
        t = ffi.new("const char[]", b"testing")
        s = ffi.new("struct foo*", [t])
        assert type(s.name) not in (bytes, str, unicode)
        assert ffi.string(s.name) == b"testing"
        with pytest.raises(TypeError):
            s.name = None
        s.name = ffi.NULL
        assert s.name == ffi.NULL

    def test_fetch_const_wchar_p_field(self):
        # 'const' is ignored so far
        ffi = FFI(backend=self.Backend())
        self.check_wchar_t(ffi)
        ffi.cdef("struct foo { const wchar_t *name; };")
        t = ffi.new("const wchar_t[]", u+"testing")
        s = ffi.new("struct foo*", [t])
        assert type(s.name) not in (bytes, str, unicode)
        assert ffi.string(s.name) == u+"testing"
        s.name = ffi.NULL
        assert s.name == ffi.NULL

    def test_voidp(self):
        ffi = FFI(backend=self.Backend())
        pytest.raises(TypeError, ffi.new, "void*")
        p = ffi.new("void **")
        assert p[0] == ffi.NULL
        a = ffi.new("int[]", [10, 11, 12])
        p = ffi.new("void **", a)
        vp = p[0]
        with pytest.raises(TypeError):
            vp[0]
        pytest.raises(TypeError, ffi.new, "short **", a)
        #
        ffi.cdef("struct foo { void *p; int *q; short *r; };")
        s = ffi.new("struct foo *")
        s.p = a    # works
        s.q = a    # works
        with pytest.raises(TypeError):
            s.r = a    # fails
        b = ffi.cast("int *", a)
        s.p = b    # works
        s.q = b    # works
        with pytest.raises(TypeError):
            s.r = b    # fails

    def test_functionptr_simple(self):
        ffi = FFI(backend=self.Backend())
        pytest.raises(TypeError, ffi.callback, "int(*)(int)", 0)
        def cb(n):
            return n + 1
        cb.__qualname__ = 'cb'
        p = ffi.callback("int(*)(int)", cb)
        res = p(41)     # calling an 'int(*)(int)', i.e. a function pointer
        assert res == 42 and type(res) is int
        res = p(ffi.cast("int", -41))
        assert res == -40 and type(res) is int
        assert repr(p).startswith(
            "<cdata 'int(*)(int)' calling <function cb at 0x")
        assert ffi.typeof(p) is ffi.typeof("int(*)(int)")
        q = ffi.new("int(**)(int)", p)
        assert repr(q) == "<cdata 'int(* *)(int)' owning %d bytes>" % (
            SIZE_OF_PTR)
        with pytest.raises(TypeError):
            q(43)
        res = q[0](43)
        assert res == 44
        q = ffi.cast("int(*)(int)", p)
        assert repr(q).startswith("<cdata 'int(*)(int)' 0x")
        res = q(45)
        assert res == 46

    def test_functionptr_advanced(self):
        ffi = FFI(backend=self.Backend())
        t = ffi.typeof("int(*(*)(int))(int)")
        assert repr(t) == self.TypeRepr % "int(*(*)(int))(int)"

    def test_functionptr_voidptr_return(self):
        ffi = FFI(backend=self.Backend())
        def cb():
            return ffi.NULL
        p = ffi.callback("void*(*)()", cb)
        res = p()
        assert res is not None
        assert res == ffi.NULL
        int_ptr = ffi.new('int*')
        void_ptr = ffi.cast('void*', int_ptr)
        def cb():
            return void_ptr
        p = ffi.callback("void*(*)()", cb)
        res = p()
        assert res == void_ptr

    def test_functionptr_intptr_return(self):
        ffi = FFI(backend=self.Backend())
        def cb():
            return ffi.NULL
        p = ffi.callback("int*(*)()", cb)
        res = p()
        assert res == ffi.NULL
        int_ptr = ffi.new('int*')
        def cb():
            return int_ptr
        p = ffi.callback("int*(*)()", cb)
        res = p()
        assert repr(res).startswith("<cdata 'int *' 0x")
        assert res == int_ptr
        int_array_ptr = ffi.new('int[1]')
        def cb():
            return int_array_ptr
        p = ffi.callback("int*(*)()", cb)
        res = p()
        assert repr(res).startswith("<cdata 'int *' 0x")
        assert res == int_array_ptr

    def test_functionptr_void_return(self):
        ffi = FFI(backend=self.Backend())
        def foo():
            pass
        foo_cb = ffi.callback("void foo()", foo)
        result = foo_cb()
        assert result is None

    def test_char_cast(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.cast("int", b'\x01')
        assert ffi.typeof(p) is ffi.typeof("int")
        assert int(p) == 1
        p = ffi.cast("int", ffi.cast("char", b"a"))
        assert int(p) == ord("a")
        p = ffi.cast("int", ffi.cast("char", b"\x80"))
        assert int(p) == 0x80     # "char" is considered unsigned in this case
        p = ffi.cast("int", b"\x81")
        assert int(p) == 0x81

    def test_wchar_cast(self):
        ffi = FFI(backend=self.Backend())
        self.check_wchar_t(ffi)
        p = ffi.cast("int", ffi.cast("wchar_t", u+'\u1234'))
        assert int(p) == 0x1234
        p = ffi.cast("long long", ffi.cast("wchar_t", -1))
        if SIZE_OF_WCHAR == 2:      # 2 bytes, unsigned
            assert int(p) == 0xffff
        elif (sys.platform.startswith('linux') and
              platform.machine().startswith('x86')):   # known to be signed
            assert int(p) == -1
        else:                     # in general, it can be either signed or not
            assert int(p) in [-1, 0xffffffff]  # e.g. on arm, both cases occur
        p = ffi.cast("int", u+'\u1234')
        assert int(p) == 0x1234

    def test_cast_array_to_charp(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short int[]", [0x1234, 0x5678])
        p = ffi.cast("char*", a)
        data = b''.join([p[i] for i in range(4)])
        if sys.byteorder == 'little':
            assert data == b'\x34\x12\x78\x56'
        else:
            assert data == b'\x12\x34\x56\x78'

    def test_cast_between_pointers(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short int[]", [0x1234, 0x5678])
        p = ffi.cast("short*", a)
        p2 = ffi.cast("int*", p)
        q = ffi.cast("char*", p2)
        data = b''.join([q[i] for i in range(4)])
        if sys.byteorder == 'little':
            assert data == b'\x34\x12\x78\x56'
        else:
            assert data == b'\x12\x34\x56\x78'

    def test_cast_pointer_and_int(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short int[]", [0x1234, 0x5678])
        l1 = ffi.cast("intptr_t", a)
        p = ffi.cast("short*", a)
        l2 = ffi.cast("intptr_t", p)
        assert int(l1) == int(l2) != 0
        q = ffi.cast("short*", l1)
        assert q == ffi.cast("short*", int(l1))
        assert q[0] == 0x1234
        assert int(ffi.cast("intptr_t", ffi.NULL)) == 0

    def test_cast_functionptr_and_int(self):
        ffi = FFI(backend=self.Backend())
        def cb(n):
            return n + 1
        a = ffi.callback("int(*)(int)", cb)
        p = ffi.cast("void *", a)
        assert p
        b = ffi.cast("int(*)(int)", p)
        assert b(41) == 42
        assert a == b
        assert hash(a) == hash(b)

    def test_callback_crash(self):
        ffi = FFI(backend=self.Backend())
        def cb(n):
            raise Exception
        a = ffi.callback("int(*)(int)", cb, error=42)
        res = a(1)    # and the error reported to stderr
        assert res == 42

    def test_structptr_argument(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo_s { int a, b; };")
        def cb(p):
            return p[0].a * 1000 + p[0].b * 100 + p[1].a * 10 + p[1].b
        a = ffi.callback("int(*)(struct foo_s[])", cb)
        res = a([[5, 6], {'a': 7, 'b': 8}])
        assert res == 5678
        res = a([[5], {'b': 8}])
        assert res == 5008

    def test_array_argument_as_list(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo_s { int a, b; };")
        seen = []
        def cb(argv):
            seen.append(ffi.string(argv[0]))
            seen.append(ffi.string(argv[1]))
        a = ffi.callback("void(*)(char *[])", cb)
        a([ffi.new("char[]", b"foobar"), ffi.new("char[]", b"baz")])
        assert seen == [b"foobar", b"baz"]

    def test_cast_float(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.cast("float", 12)
        assert float(a) == 12.0
        a = ffi.cast("float", 12.5)
        assert float(a) == 12.5
        a = ffi.cast("float", b"A")
        assert float(a) == ord("A")
        a = ffi.cast("int", 12.9)
        assert int(a) == 12
        a = ffi.cast("char", 66.9 + 256)
        assert ffi.string(a) == b"B"
        #
        a = ffi.cast("float", ffi.cast("int", 12))
        assert float(a) == 12.0
        a = ffi.cast("float", ffi.cast("double", 12.5))
        assert float(a) == 12.5
        a = ffi.cast("float", ffi.cast("char", b"A"))
        assert float(a) == ord("A")
        a = ffi.cast("int", ffi.cast("double", 12.9))
        assert int(a) == 12
        a = ffi.cast("char", ffi.cast("double", 66.9 + 256))
        assert ffi.string(a) == b"B"

    def test_enum(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("enum foo { A0, B0, CC0, D0 };")
        assert ffi.string(ffi.cast("enum foo", 0)) == "A0"
        assert ffi.string(ffi.cast("enum foo", 2)) == "CC0"
        assert ffi.string(ffi.cast("enum foo", 3)) == "D0"
        assert ffi.string(ffi.cast("enum foo", 4)) == "4"
        ffi.cdef("enum bar { A1, B1=-2, CC1, D1, E1 };")
        assert ffi.string(ffi.cast("enum bar", 0)) == "A1"
        assert ffi.string(ffi.cast("enum bar", -2)) == "B1"
        assert ffi.string(ffi.cast("enum bar", -1)) == "CC1"
        assert ffi.string(ffi.cast("enum bar", 1)) == "E1"
        assert ffi.cast("enum bar", -2) == ffi.cast("enum bar", -2)
        assert ffi.cast("enum foo", 0) == ffi.cast("enum bar", 0)
        assert ffi.cast("enum bar", 0) == ffi.cast("int", 0)
        assert repr(ffi.cast("enum bar", -1)) == "<cdata 'enum bar' -1: CC1>"
        assert repr(ffi.cast("enum foo", -1)) == (  # enums are unsigned, if
            "<cdata 'enum foo' 4294967295>")        # they contain no neg value
        ffi.cdef("enum baz { A2=0x1000, B2=0x2000 };")
        assert ffi.string(ffi.cast("enum baz", 0x1000)) == "A2"
        assert ffi.string(ffi.cast("enum baz", 0x2000)) == "B2"

    def test_enum_in_struct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("enum foo { A, B, C, D }; struct bar { enum foo e; };")
        s = ffi.new("struct bar *")
        s.e = 0
        assert s.e == 0
        s.e = 3
        assert s.e == 3
        assert s[0].e == 3
        s[0].e = 2
        assert s.e == 2
        assert s[0].e == 2
        s.e = ffi.cast("enum foo", -1)
        assert s.e == 4294967295
        assert s[0].e == 4294967295
        s.e = s.e
        with pytest.raises(TypeError):
            s.e = 'B'
        with pytest.raises(TypeError):
            s.e = '2'
        with pytest.raises(TypeError):
            s.e = '#2'
        with pytest.raises(TypeError):
            s.e = '#7'

    def test_enum_non_contiguous(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("enum foo { A, B=42, C };")
        assert ffi.string(ffi.cast("enum foo", 0)) == "A"
        assert ffi.string(ffi.cast("enum foo", 42)) == "B"
        assert ffi.string(ffi.cast("enum foo", 43)) == "C"
        invalid_value = ffi.cast("enum foo", 2)
        assert int(invalid_value) == 2
        assert ffi.string(invalid_value) == "2"

    def test_enum_char_hex_oct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef(r"enum foo{A='!', B='\'', C=0x10, D=010, E=- 0x10, F=-010};")
        assert ffi.string(ffi.cast("enum foo", ord('!'))) == "A"
        assert ffi.string(ffi.cast("enum foo", ord("'"))) == "B"
        assert ffi.string(ffi.cast("enum foo", 16)) == "C"
        assert ffi.string(ffi.cast("enum foo", 8)) == "D"
        assert ffi.string(ffi.cast("enum foo", -16)) == "E"
        assert ffi.string(ffi.cast("enum foo", -8)) == "F"

    def test_enum_partial(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef(r"enum foo {A, ...}; enum bar { B, C };")
        needs_dlopen_none()
        lib = ffi.dlopen(None)
        assert lib.B == 0
        pytest.raises(VerificationMissing, getattr, lib, "A")
        assert lib.C == 1

    def test_array_of_struct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a, b; };")
        s = ffi.new("struct foo[1]")
        with pytest.raises(AttributeError):
            s.b
        with pytest.raises(AttributeError):
            s.b = 412
        s[0].b = 412
        assert s[0].b == 412
        with pytest.raises(IndexError):
            s[1]

    def test_pointer_to_array(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int(**)[5]")
        assert repr(p) == "<cdata 'int(* *)[5]' owning %d bytes>" % SIZE_OF_PTR

    def test_iterate_array(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("char[]", b"hello")
        assert list(a) == [b"h", b"e", b"l", b"l", b"o", b"\0"]
        assert list(iter(a)) == [b"h", b"e", b"l", b"l", b"o", b"\0"]
        #
        pytest.raises(TypeError, iter, ffi.cast("char *", a))
        pytest.raises(TypeError, list, ffi.cast("char *", a))
        pytest.raises(TypeError, iter, ffi.new("int *"))
        pytest.raises(TypeError, list, ffi.new("int *"))

    def test_offsetof(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a, b, c; };")
        assert ffi.offsetof("struct foo", "a") == 0
        assert ffi.offsetof("struct foo", "b") == 4
        assert ffi.offsetof("struct foo", "c") == 8

    def test_offsetof_nested(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a, b, c; };"
                 "struct bar { struct foo d, e; };")
        assert ffi.offsetof("struct bar", "e") == 12
        pytest.raises(KeyError, ffi.offsetof, "struct bar", "e.a")
        assert ffi.offsetof("struct bar", "e", "a") == 12
        assert ffi.offsetof("struct bar", "e", "b") == 16
        assert ffi.offsetof("struct bar", "e", "c") == 20

    def test_offsetof_array(self):
        ffi = FFI(backend=self.Backend())
        assert ffi.offsetof("int[]", 51) == 51 * ffi.sizeof("int")
        assert ffi.offsetof("int *", 51) == 51 * ffi.sizeof("int")
        ffi.cdef("struct bar { int a, b; int c[99]; };")
        assert ffi.offsetof("struct bar", "c") == 2 * ffi.sizeof("int")
        assert ffi.offsetof("struct bar", "c", 0) == 2 * ffi.sizeof("int")
        assert ffi.offsetof("struct bar", "c", 51) == 53 * ffi.sizeof("int")

    def test_alignof(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { char a; short b; char c; };")
        assert ffi.alignof("int") == 4
        assert ffi.alignof("double") in (4, 8)
        assert ffi.alignof("struct foo") == 2

    def test_bitfield(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a:10, b:20, c:3; };")
        assert ffi.sizeof("struct foo") == 8
        s = ffi.new("struct foo *")
        s.a = 511
        with pytest.raises(OverflowError):
            s.a = 512
        with pytest.raises(OverflowError):
            s[0].a = 512
        assert s.a == 511
        s.a = -512
        with pytest.raises(OverflowError):
            s.a = -513
        with pytest.raises(OverflowError):
            s[0].a = -513
        assert s.a == -512
        s.c = 3
        assert s.c == 3
        with pytest.raises(OverflowError):
            s.c = 4
        with pytest.raises(OverflowError):
            s[0].c = 4
        s.c = -4
        assert s.c == -4

    def test_bitfield_enum(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            typedef enum { AA, BB, CC } foo_e;
            typedef struct { foo_e f:2; } foo_s;
        """)
        s = ffi.new("foo_s *")
        s.f = 2
        assert s.f == 2

    def test_anonymous_struct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("typedef struct { int a; } foo_t;")
        ffi.cdef("typedef struct { char b, c; } bar_t;")
        f = ffi.new("foo_t *", [12345])
        b = ffi.new("bar_t *", [b"B", b"C"])
        assert f.a == 12345
        assert b.b == b"B"
        assert b.c == b"C"
        assert repr(b).startswith("<cdata 'bar_t *'")

    def test_struct_with_two_usages(self):
        for name in ['foo_s', '']:    # anonymous or not
            ffi = FFI(backend=self.Backend())
            ffi.cdef("typedef struct %s { int a; } foo_t, *foo_p;" % name)
            f = ffi.new("foo_t *", [12345])
            ps = ffi.new("foo_p[]", [f])

    def test_pointer_arithmetic(self):
        ffi = FFI(backend=self.Backend())
        s = ffi.new("short[]", list(range(100, 110)))
        p = ffi.cast("short *", s)
        assert p[2] == 102
        assert p+1 == p+1
        assert p+1 != p+0
        assert p == p+0 == p-0
        assert (p+1)[0] == 101
        assert (p+19)[-10] == 109
        assert (p+5) - (p+1) == 4
        assert p == s+0
        assert p+1 == s+1

    def test_pointer_comparison(self):
        ffi = FFI(backend=self.Backend())
        s = ffi.new("short[]", list(range(100)))
        p = ffi.cast("short *", s)
        assert (p <  s) is False
        assert (p <= s) is True
        assert (p == s) is True
        assert (p != s) is False
        assert (p >  s) is False
        assert (p >= s) is True
        assert (s <  p) is False
        assert (s <= p) is True
        assert (s == p) is True
        assert (s != p) is False
        assert (s >  p) is False
        assert (s >= p) is True
        q = p + 1
        assert (q <  s) is False
        assert (q <= s) is False
        assert (q == s) is False
        assert (q != s) is True
        assert (q >  s) is True
        assert (q >= s) is True
        assert (s <  q) is True
        assert (s <= q) is True
        assert (s == q) is False
        assert (s != q) is True
        assert (s >  q) is False
        assert (s >= q) is False
        assert (q <  p) is False
        assert (q <= p) is False
        assert (q == p) is False
        assert (q != p) is True
        assert (q >  p) is True
        assert (q >= p) is True
        assert (p <  q) is True
        assert (p <= q) is True
        assert (p == q) is False
        assert (p != q) is True
        assert (p >  q) is False
        assert (p >= q) is False
        #
        assert (None == s) is False
        assert (None != s) is True
        assert (s == None) is False
        assert (s != None) is True
        assert (None == q) is False
        assert (None != q) is True
        assert (q == None) is False
        assert (q != None) is True

    def test_integer_comparison(self):
        ffi = FFI(backend=self.Backend())
        x = ffi.cast("int", 123)
        y = ffi.cast("int", 456)
        assert x < y
        #
        z = ffi.cast("double", 78.9)
        assert x > z
        assert y > z

    def test_ffi_buffer_ptr(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short *", 100)
        try:
            b = ffi.buffer(a)
        except NotImplementedError as e:
            pytest.skip(str(e))
        assert type(b) is ffi.buffer
        content = b[:]
        assert len(content) == len(b) == 2
        if sys.byteorder == 'little':
            assert content == b'\x64\x00'
            assert b[0] == b'\x64'
            b[0] = b'\x65'
        else:
            assert content == b'\x00\x64'
            assert b[1] == b'\x64'
            b[1] = b'\x65'
        assert a[0] == 101

    def test_ffi_buffer_array(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("int[]", list(range(100, 110)))
        try:
            b = ffi.buffer(a)
        except NotImplementedError as e:
            pytest.skip(str(e))
        content = b[:]
        if sys.byteorder == 'little':
            assert content.startswith(b'\x64\x00\x00\x00\x65\x00\x00\x00')
            b[4] = b'\x45'
        else:
            assert content.startswith(b'\x00\x00\x00\x64\x00\x00\x00\x65')
            b[7] = b'\x45'
        assert len(content) == 4 * 10
        assert a[1] == 0x45

    def test_ffi_buffer_ptr_size(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short *", 0x4243)
        try:
            b = ffi.buffer(a, 1)
        except NotImplementedError as e:
            pytest.skip(str(e))
        content = b[:]
        assert len(content) == 1
        if sys.byteorder == 'little':
            assert content == b'\x43'
            b[0] = b'\x62'
            assert a[0] == 0x4262
        else:
            assert content == b'\x42'
            b[0] = b'\x63'
            assert a[0] == 0x6343

    def test_ffi_buffer_array_size(self):
        ffi = FFI(backend=self.Backend())
        a1 = ffi.new("int[]", list(range(100, 110)))
        a2 = ffi.new("int[]", list(range(100, 115)))
        try:
            ffi.buffer(a1)
        except NotImplementedError as e:
            pytest.skip(str(e))
        assert ffi.buffer(a1)[:] == ffi.buffer(a2, 4*10)[:]

    def test_ffi_buffer_with_file(self):
        ffi = FFI(backend=self.Backend())
        import tempfile, os, array
        fd, filename = tempfile.mkstemp()
        f = os.fdopen(fd, 'r+b')
        a = ffi.new("int[]", list(range(1005)))
        try:
            ffi.buffer(a, 512)
        except NotImplementedError as e:
            pytest.skip(str(e))
        f.write(ffi.buffer(a, 1000 * ffi.sizeof("int")))
        f.seek(0)
        assert f.read() == arraytostring(array.array('i', range(1000)))
        f.seek(0)
        b = ffi.new("int[]", 1005)
        f.readinto(ffi.buffer(b, 1000 * ffi.sizeof("int")))
        assert list(a)[:1000] + [0] * (len(a)-1000) == list(b)
        f.close()
        os.unlink(filename)

    def test_ffi_buffer_with_io(self):
        ffi = FFI(backend=self.Backend())
        import io, array
        f = io.BytesIO()
        a = ffi.new("int[]", list(range(1005)))
        try:
            ffi.buffer(a, 512)
        except NotImplementedError as e:
            pytest.skip(str(e))
        f.write(ffi.buffer(a, 1000 * ffi.sizeof("int")))
        f.seek(0)
        assert f.read() == arraytostring(array.array('i', range(1000)))
        f.seek(0)
        b = ffi.new("int[]", 1005)
        f.readinto(ffi.buffer(b, 1000 * ffi.sizeof("int")))
        assert list(a)[:1000] + [0] * (len(a)-1000) == list(b)
        f.close()

    def test_ffi_buffer_comparisons(self):
        ffi = FFI(backend=self.Backend())
        ba = bytearray(range(100, 110))
        if sys.version_info >= (2, 7):
            assert ba == memoryview(ba)    # justification for the following
        a = ffi.new("uint8_t[]", list(ba))
        c = ffi.new("uint8_t[]", [99] + list(ba))
        try:
            b_full = ffi.buffer(a)
            b_short = ffi.buffer(a, 3)
            b_mid = ffi.buffer(a, 6)
            b_other = ffi.buffer(c, 6)
        except NotImplementedError as e:
            pytest.skip(str(e))
        else:
            content = b_full[:]
            assert content == b_full == ba
            assert b_other < b_short < b_mid < b_full
            assert ba > b_mid > ba[0:2]
            assert b_short != ba[1:4]

    def test_array_in_struct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo_s { int len; short data[5]; };")
        p = ffi.new("struct foo_s *")
        p.data[3] = 5
        assert p.data[3] == 5
        assert repr(p.data).startswith("<cdata 'short[5]' 0x")

    def test_struct_containing_array_varsize_workaround(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo_s { int len; short data[0]; };")
        p = ffi.new("char[]", ffi.sizeof("struct foo_s") + 7 * SIZE_OF_SHORT)
        q = ffi.cast("struct foo_s *", p)
        assert q.len == 0
        # 'q.data' gets not a 'short[0]', but just a 'short *' instead
        assert repr(q.data).startswith("<cdata 'short *' 0x")
        assert q.data[6] == 0
        q.data[6] = 15
        assert q.data[6] == 15

    def test_new_struct_containing_array_varsize(self):
        pytest.skip("later?")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo_s { int len; short data[]; };")
        p = ffi.new("struct foo_s *", 10)     # a single integer is the length
        assert p.len == 0
        assert p.data[9] == 0
        with pytest.raises(IndexError):
            p.data[10]

    def test_ffi_typeof_getcname(self):
        ffi = FFI(backend=self.Backend())
        assert ffi.getctype("int") == "int"
        assert ffi.getctype("int", 'x') == "int x"
        assert ffi.getctype("int*") == "int *"
        assert ffi.getctype("int*", '') == "int *"
        assert ffi.getctype("int*", 'x') == "int * x"
        assert ffi.getctype("int", '*') == "int *"
        assert ffi.getctype("int", ' * x ') == "int * x"
        assert ffi.getctype(ffi.typeof("int*"), '*') == "int * *"
        assert ffi.getctype("int", '[5]') == "int[5]"
        assert ffi.getctype("int[5]", '[6]') == "int[6][5]"
        assert ffi.getctype("int[5]", '(*)') == "int(*)[5]"
        # special-case for convenience: automatically put '()' around '*'
        assert ffi.getctype("int[5]", '*') == "int(*)[5]"
        assert ffi.getctype("int[5]", '*foo') == "int(*foo)[5]"
        assert ffi.getctype("int[5]", ' ** foo ') == "int(** foo)[5]"

    def test_array_of_func_ptr(self):
        ffi = FFI(backend=self.Backend())
        f = ffi.cast("int(*)(int)", 42)
        assert f != ffi.NULL
        pytest.raises(CDefError, ffi.cast, "int(int)", 42)
        pytest.raises(CDefError, ffi.new, "int([5])(int)")
        a = ffi.new("int(*[5])(int)", [f])
        assert ffi.getctype(ffi.typeof(a)) == "int(*[5])(int)"
        assert len(a) == 5
        assert a[0] == f
        assert a[1] == ffi.NULL
        pytest.raises(TypeError, ffi.cast, "int(*)(int)[5]", 0)
        #
        def cb(n):
            return n + 1
        f = ffi.callback("int(*)(int)", cb)
        a = ffi.new("int(*[5])(int)", [f, f])
        assert a[1](42) == 43

    def test_callback_as_function_argument(self):
        # In C, function arguments can be declared with a function type,
        # which is automatically replaced with the ptr-to-function type.
        ffi = FFI(backend=self.Backend())
        def cb(a, b):
            return chr(ord(a) + ord(b)).encode()
        f = ffi.callback("char cb(char, char)", cb)
        assert f(b'A', b'\x01') == b'B'
        def g(callback):
            return callback(b'A', b'\x01')
        g = ffi.callback("char g(char cb(char, char))", g)
        assert g(f) == b'B'

    def test_vararg_callback(self):
        pytest.skip("callback with '...'")
        ffi = FFI(backend=self.Backend())
        def cb(i, va_list):
            j = ffi.va_arg(va_list, "int")
            k = ffi.va_arg(va_list, "long long")
            return i * 2 + j * 3 + k * 5
        f = ffi.callback("long long cb(long i, ...)", cb)
        res = f(10, ffi.cast("int", 100), ffi.cast("long long", 1000))
        assert res == 20 + 300 + 5000

    def test_callback_decorator(self):
        ffi = FFI(backend=self.Backend())
        #
        @ffi.callback("long(long, long)", error=42)
        def cb(a, b):
            return a - b
        #
        assert cb(-100, -10) == -90
        sz = ffi.sizeof("long")
        assert cb((1 << (sz*8-1)) - 1, -10) == 42

    def test_unique_types(self):
        ffi1 = FFI(backend=self.Backend())
        ffi2 = FFI(backend=self.Backend())
        assert ffi1.typeof("char") is ffi2.typeof("char ")
        assert ffi1.typeof("long") is ffi2.typeof("signed long int")
        assert ffi1.typeof("double *") is ffi2.typeof("double*")
        assert ffi1.typeof("int ***") is ffi2.typeof(" int * * *")
        assert ffi1.typeof("int[]") is ffi2.typeof("signed int[]")
        assert ffi1.typeof("signed int*[17]") is ffi2.typeof("int *[17]")
        assert ffi1.typeof("void") is ffi2.typeof("void")
        assert ffi1.typeof("int(*)(int,int)") is ffi2.typeof("int(*)(int,int)")
        #
        # these depend on user-defined data, so should not be shared
        assert ffi1.typeof("struct foo") is not ffi2.typeof("struct foo")
        assert ffi1.typeof("union foo *") is not ffi2.typeof("union foo*")
        # the following test is an opaque enum, which we no longer support
        #assert ffi1.typeof("enum foo") is not ffi2.typeof("enum foo")
        # sanity check: twice 'ffi1'
        assert ffi1.typeof("struct foo*") is ffi1.typeof("struct foo *")

    def test_anonymous_enum(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("typedef enum { Value0 = 0 } e, *pe;\n"
                 "typedef enum { Value1 = 1 } e1;")
        assert ffi.getctype("e*") == 'e *'
        assert ffi.getctype("pe") == 'e *'
        assert ffi.getctype("e1*") == 'e1 *'

    def test_opaque_enum(self):
        import warnings
        ffi = FFI(backend=self.Backend())
        ffi.cdef("enum foo;")
        with warnings.catch_warnings(record=True) as log:
            warnings.simplefilter("always")
            n = ffi.cast("enum foo", -1)
            assert int(n) == 0xffffffff
        assert str(log[0].message) == (
            "'enum foo' has no values explicitly defined; "
            "guessing that it is equivalent to 'unsigned int'")

    def test_new_ctype(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int *")
        pytest.raises(TypeError, ffi.new, p)
        p = ffi.new(ffi.typeof("int *"), 42)
        assert p[0] == 42

    def test_enum_with_non_injective_mapping(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("enum e { AA=0, BB=0, CC=0, DD=0 };")
        e = ffi.cast("enum e", 0)
        assert ffi.string(e) == "AA"     # pick the first one arbitrarily

    def test_enum_refer_previous_enum_value(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("enum e { AA, BB=2, CC=4, DD=BB, EE, FF=CC, GG=FF };")
        assert ffi.string(ffi.cast("enum e", 2)) == "BB"
        assert ffi.string(ffi.cast("enum e", 3)) == "EE"
        assert ffi.sizeof("char[DD]") == 2
        assert ffi.sizeof("char[EE]") == 3
        assert ffi.sizeof("char[FF]") == 4
        assert ffi.sizeof("char[GG]") == 4

    def test_nested_anonymous_struct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            struct foo_s {
                struct { int a, b; };
                union { int c, d; };
            };
        """)
        assert ffi.sizeof("struct foo_s") == 3 * SIZE_OF_INT
        p = ffi.new("struct foo_s *", [1, 2, 3])
        assert p.a == 1
        assert p.b == 2
        assert p.c == 3
        assert p.d == 3
        p.d = 17
        assert p.c == 17
        p.b = 19
        assert p.a == 1
        assert p.b == 19
        assert p.c == 17
        assert p.d == 17
        p = ffi.new("struct foo_s *", {'b': 12, 'd': 14})
        assert p.a == 0
        assert p.b == 12
        assert p.c == 14
        assert p.d == 14
        pytest.raises(ValueError, ffi.new, "struct foo_s *", [0, 0, 0, 0])

    def test_nested_field_offset_align(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            struct foo_s {
                struct { int a; char b; };
                union { char c; };
            };
        """)
        assert ffi.offsetof("struct foo_s", "c") == 2 * SIZE_OF_INT
        assert ffi.sizeof("struct foo_s") == 3 * SIZE_OF_INT

    def test_nested_anonymous_union(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            union foo_u {
                struct { int a, b; };
                union { int c, d; };
            };
        """)
        assert ffi.sizeof("union foo_u") == 2 * SIZE_OF_INT
        p = ffi.new("union foo_u *", [5])
        assert p.a == 5
        assert p.b == 0
        assert p.c == 5
        assert p.d == 5
        p.d = 17
        assert p.c == 17
        assert p.a == 17
        p.b = 19
        assert p.a == 17
        assert p.b == 19
        assert p.c == 17
        assert p.d == 17
        p = ffi.new("union foo_u *", {'d': 14})
        assert p.a == 14
        assert p.b == 0
        assert p.c == 14
        assert p.d == 14
        p = ffi.new("union foo_u *", {'a': -63, 'b': 12})
        assert p.a == -63
        assert p.b == 12
        assert p.c == -63
        assert p.d == -63
        p = ffi.new("union foo_u *", [123, 456])
        assert p.a == 123
        assert p.b == 456
        assert p.c == 123
        assert p.d == 123
        pytest.raises(ValueError, ffi.new, "union foo_u *", [0, 0, 0])

    def test_nested_anonymous_struct_2(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            struct foo_s {
                int a;
                union { int b; union { int c, d; }; };
                int e;
            };
        """)
        assert ffi.sizeof("struct foo_s") == 3 * SIZE_OF_INT
        p = ffi.new("struct foo_s *", [11, 22, 33])
        assert p.a == 11
        assert p.b == p.c == p.d == 22
        assert p.e == 33
        pytest.raises(ValueError, ffi.new, "struct foo_s *", [11, 22, 33, 44])
        FOO = ffi.typeof("struct foo_s")
        fields = [(name, fld.offset, fld.flags) for (name, fld) in FOO.fields]
        assert fields == [
            ('a', 0 * SIZE_OF_INT, 0),
            ('b', 1 * SIZE_OF_INT, 0),
            ('c', 1 * SIZE_OF_INT, 1),
            ('d', 1 * SIZE_OF_INT, 1),
            ('e', 2 * SIZE_OF_INT, 0),
        ]

    def test_cast_to_array_type(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[4]", [-5])
        q = ffi.cast("int[3]", p)
        assert q[0] == -5
        assert repr(q).startswith("<cdata 'int[3]' 0x")

    def test_gc(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int *", 123)
        seen = []
        def destructor(p1):
            assert p1 is p
            assert p1[0] == 123
            seen.append(1)
        q = ffi.gc(p, destructor)
        assert ffi.typeof(q) is ffi.typeof(p)
        import gc; gc.collect()
        assert seen == []
        del q
        import gc; gc.collect(); gc.collect(); gc.collect()
        assert seen == [1]

    def test_gc_2(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int *", 123)
        seen = []
        q1 = ffi.gc(p, lambda p: seen.append(1))
        q2 = ffi.gc(q1, lambda p: seen.append(2))
        import gc; gc.collect()
        assert seen == []
        del q1, q2
        import gc; gc.collect(); gc.collect(); gc.collect(); gc.collect()
        assert seen == [2, 1]

    def test_gc_3(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int *", 123)
        r = ffi.new("int *", 123)
        seen = []
        seen_r = []
        q1 = ffi.gc(p, lambda p: seen.append(1))
        s1 = ffi.gc(r, lambda r: seen_r.append(4))
        q2 = ffi.gc(q1, lambda p: seen.append(2))
        s2 = ffi.gc(s1, lambda r: seen_r.append(5))
        q3 = ffi.gc(q2, lambda p: seen.append(3))
        import gc; gc.collect()
        assert seen == []
        assert seen_r == []
        del q1, q2, q3, s2, s1
        import gc; gc.collect(); gc.collect(); gc.collect(); gc.collect()
        assert seen == [3, 2, 1]
        assert seen_r == [5, 4]

    def test_gc_4(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int *", 123)
        seen = []
        q1 = ffi.gc(p, lambda p: seen.append(1))
        q2 = ffi.gc(q1, lambda p: seen.append(2))
        q3 = ffi.gc(q2, lambda p: seen.append(3))
        import gc; gc.collect()
        assert seen == []
        del q1, q3     # q2 remains, and has a hard ref to q1
        import gc; gc.collect(); gc.collect(); gc.collect()
        assert seen == [3]

    def test_gc_disable(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int *", 123)
        pytest.raises(TypeError, ffi.gc, p, None)
        seen = []
        q1 = ffi.gc(p, lambda p: seen.append(1))
        q2 = ffi.gc(q1, lambda p: seen.append(2))
        import gc; gc.collect()
        assert seen == []
        assert ffi.gc(q1, None) is None
        del q1, q2
        import gc; gc.collect(); gc.collect(); gc.collect()
        assert seen == [2]

    def test_gc_finite_list(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int *", 123)
        keepalive = []
        for i in range(10):
            keepalive.append(ffi.gc(p, lambda p: None))
        del keepalive[:]
        import gc; gc.collect(); gc.collect()
        for i in range(10):
            keepalive.append(ffi.gc(p, lambda p: None))

    def test_CData_CType(self):
        ffi = FFI(backend=self.Backend())
        assert isinstance(ffi.cast("int", 0), ffi.CData)
        assert isinstance(ffi.new("int *"), ffi.CData)
        assert not isinstance(ffi.typeof("int"), ffi.CData)
        assert not isinstance(ffi.cast("int", 0), ffi.CType)
        assert not isinstance(ffi.new("int *"), ffi.CType)

    def test_CData_CType_2(self):
        ffi = FFI(backend=self.Backend())
        assert isinstance(ffi.typeof("int"), ffi.CType)

    def test_bool(self):
        ffi = FFI(backend=self.Backend())
        assert int(ffi.cast("_Bool", 0.1)) == 1
        assert int(ffi.cast("_Bool", -0.0)) == 0
        assert int(ffi.cast("_Bool", b'\x02')) == 1
        assert int(ffi.cast("_Bool", b'\x00')) == 0
        assert int(ffi.cast("_Bool", b'\x80')) == 1
        assert ffi.new("_Bool *", False)[0] == 0
        assert ffi.new("_Bool *", 1)[0] == 1
        pytest.raises(OverflowError, ffi.new, "_Bool *", 2)
        pytest.raises(TypeError, ffi.string, ffi.cast("_Bool", 2))

    def test_use_own_bool(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""typedef int bool;""")

    def test_ordering_bug1(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            struct foo_s {
                struct bar_s *p;
            };
            struct bar_s {
                struct foo_s foo;
            };
        """)
        q = ffi.new("struct foo_s *")
        bar = ffi.new("struct bar_s *")
        q.p = bar
        assert q.p.foo.p == ffi.NULL

    def test_ordering_bug2(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            struct bar_s;

            struct foo_s {
                void (*foo)(struct bar_s[]);
            };

            struct bar_s {
                struct foo_s foo;
            };
        """)
        q = ffi.new("struct foo_s *")

    def test_addressof(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo_s { int x, y; };")
        p = ffi.new("struct foo_s *")
        a = ffi.addressof(p[0])
        assert repr(a).startswith("<cdata 'struct foo_s *' 0x")
        assert a == p
        pytest.raises(TypeError, ffi.addressof, p)
        pytest.raises((AttributeError, TypeError), ffi.addressof, 5)
        pytest.raises(TypeError, ffi.addressof, ffi.cast("int", 5))

    def test_addressof_field(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo_s { int x, y; };")
        p = ffi.new("struct foo_s *")
        a = ffi.addressof(p[0], 'y')
        assert repr(a).startswith("<cdata 'int *' 0x")
        assert int(ffi.cast("uintptr_t", a)) == (
            int(ffi.cast("uintptr_t", p)) + ffi.sizeof("int"))
        assert a == ffi.addressof(p, 'y')
        assert a != ffi.addressof(p, 'x')

    def test_addressof_field_nested(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo_s { int x, y; };"
                 "struct bar_s { struct foo_s a, b; };")
        p = ffi.new("struct bar_s *")
        pytest.raises(KeyError, ffi.addressof, p[0], 'b.y')
        a = ffi.addressof(p[0], 'b', 'y')
        assert int(ffi.cast("uintptr_t", a)) == (
            int(ffi.cast("uintptr_t", p)) +
            ffi.sizeof("struct foo_s") + ffi.sizeof("int"))

    def test_addressof_anonymous_struct(self):
        ffi = FFI()
        ffi.cdef("typedef struct { int x; } foo_t;")
        p = ffi.new("foo_t *")
        a = ffi.addressof(p[0])
        assert a == p

    def test_addressof_array(self):
        ffi = FFI()
        p = ffi.new("int[52]")
        p0 = ffi.addressof(p)
        assert p0 == p
        assert ffi.typeof(p0) is ffi.typeof("int(*)[52]")
        pytest.raises(TypeError, ffi.addressof, p0)
        #
        p1 = ffi.addressof(p, 25)
        assert ffi.typeof(p1) is ffi.typeof("int *")
        assert (p1 - p) == 25
        assert ffi.addressof(p, 0) == p

    def test_addressof_pointer(self):
        ffi = FFI()
        array = ffi.new("int[50]")
        p = ffi.cast("int *", array)
        pytest.raises(TypeError, ffi.addressof, p)
        assert ffi.addressof(p, 0) == p
        assert ffi.addressof(p, 25) == p + 25
        assert ffi.typeof(ffi.addressof(p, 25)) == ffi.typeof(p)
        #
        ffi.cdef("struct foo { int a, b; };")
        array = ffi.new("struct foo[50]")
        p = ffi.cast("int *", array)
        pytest.raises(TypeError, ffi.addressof, p)
        assert ffi.addressof(p, 0) == p
        assert ffi.addressof(p, 25) == p + 25
        assert ffi.typeof(ffi.addressof(p, 25)) == ffi.typeof(p)

    def test_addressof_array_in_struct(self):
        ffi = FFI()
        ffi.cdef("struct foo { int a, b; int c[50]; };")
        p = ffi.new("struct foo *")
        p1 = ffi.addressof(p, "c", 25)
        assert ffi.typeof(p1) is ffi.typeof("int *")
        assert p1 == ffi.cast("int *", p) + 27
        assert ffi.addressof(p, "c") == ffi.cast("int *", p) + 2
        assert ffi.addressof(p, "c", 0) == ffi.cast("int *", p) + 2
        p2 = ffi.addressof(p, 1)
        assert ffi.typeof(p2) is ffi.typeof("struct foo *")
        assert p2 == p + 1

    def test_multiple_independent_structs(self):
        ffi1 = FFI(); ffi1.cdef("struct foo { int x; };")
        ffi2 = FFI(); ffi2.cdef("struct foo { int y, z; };")
        foo1 = ffi1.new("struct foo *", [10])
        foo2 = ffi2.new("struct foo *", [20, 30])
        assert foo1.x == 10
        assert foo2.y == 20
        assert foo2.z == 30

    def test_missing_include(self):
        backend = self.Backend()
        ffi1 = FFI(backend=backend)
        ffi2 = FFI(backend=backend)
        ffi1.cdef("typedef signed char schar_t;")
        pytest.raises(CDefError, ffi2.cast, "schar_t", 142)

    def test_include_typedef(self):
        backend = self.Backend()
        ffi1 = FFI(backend=backend)
        ffi2 = FFI(backend=backend)
        ffi1.cdef("typedef signed char schar_t;")
        ffi2.include(ffi1)
        p = ffi2.cast("schar_t", 142)
        assert int(p) == 142 - 256

    def test_include_struct(self):
        backend = self.Backend()
        ffi1 = FFI(backend=backend)
        ffi2 = FFI(backend=backend)
        ffi1.cdef("struct foo { int x; };")
        ffi2.include(ffi1)
        p = ffi2.new("struct foo *", [142])
        assert p.x == 142

    def test_include_union(self):
        backend = self.Backend()
        ffi1 = FFI(backend=backend)
        ffi2 = FFI(backend=backend)
        ffi1.cdef("union foo { int x; };")
        ffi2.include(ffi1)
        p = ffi2.new("union foo *", [142])
        assert p.x == 142

    def test_include_enum(self):
        backend = self.Backend()
        ffi1 = FFI(backend=backend)
        ffi2 = FFI(backend=backend)
        ffi1.cdef("enum foo { FA, FB, FC };")
        ffi2.include(ffi1)
        p = ffi2.cast("enum foo", 1)
        assert ffi2.string(p) == "FB"
        assert ffi2.sizeof("char[FC]") == 2

    def test_include_typedef_2(self):
        backend = self.Backend()
        ffi1 = FFI(backend=backend)
        ffi2 = FFI(backend=backend)
        ffi1.cdef("typedef struct { int x; } *foo_p;")
        ffi2.include(ffi1)
        p = ffi2.new("foo_p", [142])
        assert p.x == 142

    def test_ignore_multiple_declarations_of_constant(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("#define FOO 42")
        ffi.cdef("#define FOO 42")
        pytest.raises(FFIError, ffi.cdef, "#define FOO 43")

    def test_struct_packed(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct nonpacked { char a; int b; };")
        ffi.cdef("struct is_packed { char a; int b; };", packed=True)
        ffi.cdef("struct is_packed1 { char a; int b; };", pack=1)
        ffi.cdef("struct is_packed2 { char a; int b; };", pack=2)
        ffi.cdef("struct is_packed4 { char a; int b; };", pack=4)
        ffi.cdef("struct is_packed8 { char a; int b; };", pack=8)
        assert ffi.sizeof("struct nonpacked") == 8
        assert ffi.sizeof("struct is_packed") == 5
        assert ffi.sizeof("struct is_packed1") == 5
        assert ffi.sizeof("struct is_packed2") == 6
        assert ffi.sizeof("struct is_packed4") == 8
        assert ffi.sizeof("struct is_packed8") == 8
        assert ffi.alignof("struct nonpacked") == 4
        assert ffi.alignof("struct is_packed") == 1
        assert ffi.alignof("struct is_packed1") == 1
        assert ffi.alignof("struct is_packed2") == 2
        assert ffi.alignof("struct is_packed4") == 4
        assert ffi.alignof("struct is_packed8") == 4
        for name in ['is_packed', 'is_packed1', 'is_packed2',
                     'is_packed4', 'is_packed8']:
            s = ffi.new("struct %s[2]" % name)
            s[0].b = 42623381
            s[0].a = b'X'
            s[1].b = -4892220
            s[1].a = b'Y'
            assert s[0].b == 42623381
            assert s[0].a == b'X'
            assert s[1].b == -4892220
            assert s[1].a == b'Y'

    def test_pack_valueerror(self):
        ffi = FFI(backend=self.Backend())
        pytest.raises(ValueError, ffi.cdef, "", pack=3)
        pytest.raises(ValueError, ffi.cdef, "", packed=2)
        pytest.raises(ValueError, ffi.cdef, "", packed=True, pack=1)

    def test_define_integer_constant(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            #define DOT_0 0
            #define DOT 100
            #define DOT_OCT 0100l
            #define DOT_HEX 0x100u
            #define DOT_HEX2 0X10
            #define DOT_UL 1000UL
            enum foo {AA, BB=DOT, CC};
        """)
        needs_dlopen_none()
        lib = ffi.dlopen(None)
        assert ffi.string(ffi.cast("enum foo", 100)) == "BB"
        assert lib.DOT_0 == 0
        assert lib.DOT == 100
        assert lib.DOT_OCT == 0o100
        assert lib.DOT_HEX == 0x100
        assert lib.DOT_HEX2 == 0x10
        assert lib.DOT_UL == 1000

    def test_opaque_struct_becomes_nonopaque(self):
        # Issue #193: if we use a struct between the first cdef() where it is
        # declared and another cdef() where its fields are defined, then the
        # definition was ignored.
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo_s;")
        pytest.raises(TypeError, ffi.new, "struct foo_s *")
        ffi.cdef("struct foo_s { int x; };")
        ffi.new("struct foo_s *")

    def test_ffi_self_include(self):
        ffi = FFI(backend=self.Backend())
        pytest.raises(ValueError, ffi.include, ffi)

    def test_anonymous_enum_include(self):
        ffi1 = FFI()
        ffi1.cdef("enum { EE1 };")
        ffi = FFI()
        ffi.include(ffi1)
        ffi.cdef("enum { EE2, EE3 };")
        needs_dlopen_none()
        lib = ffi.dlopen(None)
        assert lib.EE1 == 0
        assert lib.EE2 == 0
        assert lib.EE3 == 1

    def test_init_once(self):
        def do_init():
            seen.append(1)
            return 42
        ffi = FFI()
        seen = []
        for i in range(3):
            res = ffi.init_once(do_init, "tag1")
            assert res == 42
            assert seen == [1]
        for i in range(3):
            res = ffi.init_once(do_init, "tag2")
            assert res == 42
            assert seen == [1, 1]

    def test_init_once_multithread(self):
        import sys, time
        if sys.version_info < (3,):
            import thread
        else:
            import _thread as thread
        #
        def do_init():
            seen.append('init!')
            time.sleep(1)
            seen.append('init done')
            return 7
        ffi = FFI()
        seen = []
        for i in range(6):
            def f():
                res = ffi.init_once(do_init, "tag")
                seen.append(res)
            thread.start_new_thread(f, ())
        time.sleep(1.5)
        assert seen == ['init!', 'init done'] + 6 * [7]

    def test_sizeof_struct_directly(self):
        # only works with the Python FFI instances
        ffi = FFI(backend=self.Backend())
        assert ffi.sizeof("struct{int a;}") == ffi.sizeof("int")

    def test_callback_large_struct(self):
        ffi = FFI(backend=self.Backend())
        # more than 8 bytes
        ffi.cdef("struct foo_s { unsigned long a, b, c; };")
        #
        @ffi.callback("void(struct foo_s)")
        def cb(s):
            seen.append(ffi.typeof(s))
            s.a += 1
            s.b += 2
            s.c += 3
            seen.append(s.a)
            seen.append(s.b)
            seen.append(s.c)
        #
        s1 = ffi.new("struct foo_s *", {'a': 100, 'b': 200, 'c': 300})
        seen = []
        cb(s1[0])
        assert len(seen) == 4
        assert s1.a == 100     # unmodified
        assert s1.b == 200
        assert s1.c == 300
        assert seen[0] == ffi.typeof("struct foo_s")
        assert seen[1] == 101
        assert seen[2] == 202
        assert seen[3] == 303

    def test_ffi_array_as_init(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[4]", [10, 20, 30, 400])
        q = ffi.new("int[4]", p)
        assert list(q) == [10, 20, 30, 400]
        pytest.raises(TypeError, ffi.new, "int[3]", p)
        pytest.raises(TypeError, ffi.new, "int[5]", p)
        pytest.raises(TypeError, ffi.new, "int16_t[4]", p)
        s = ffi.new("struct {int i[4];}*", {'i': p})
        assert list(s.i) == [10, 20, 30, 400]

    def test_too_many_initializers(self):
        ffi = FFI(backend=self.Backend())
        pytest.raises(IndexError, ffi.new, "int[4]", [10, 20, 30, 40, 50])
