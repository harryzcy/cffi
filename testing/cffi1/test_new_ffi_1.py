import pytest
import platform
import sys, os, ctypes
import cffi
from testing.udir import udir
from testing.support import *
from cffi.recompiler import recompile, NativeIO
from cffi.cffi_opcode import PRIMITIVE_TO_INDEX

SIZE_OF_INT   = ctypes.sizeof(ctypes.c_int)
SIZE_OF_LONG  = ctypes.sizeof(ctypes.c_long)
SIZE_OF_SHORT = ctypes.sizeof(ctypes.c_short)
SIZE_OF_PTR   = ctypes.sizeof(ctypes.c_void_p)
SIZE_OF_WCHAR = ctypes.sizeof(ctypes.c_wchar)


def setup_module():
    global ffi, construction_params
    ffi1 = cffi.FFI()
    DEFS = r"""
        struct repr { short a, b, c; };
        struct simple { int a; short b, c; };
        struct array { int a[2]; char b[3]; };
        struct recursive { int value; struct recursive *next; };
        union simple_u { int a; short b, c; };
        union init_u { char a; int b; };
        struct four_s { int a; short b, c, d; };
        union four_u { int a; short b, c, d; };
        struct string { const char *name; };
        struct ustring { const wchar_t *name; };
        struct voidp { void *p; int *q; short *r; };
        struct ab { int a, b; };
        struct abc { int a, b, c; };

        /* don't use A0, B0, CC0, D0 because termios.h might be included
           and it has its own #defines for these names */
        enum foq { cffiA0, cffiB0, cffiCC0, cffiD0 };
        enum bar { A1, B1=-2, CC1, D1, E1 };
        enum baz { A2=0x1000, B2=0x2000 };
        enum foo2 { A3, B3, C3, D3 };
        struct bar_with_e { enum foo2 e; };
        enum noncont { A4, B4=42, C4 };
        enum etypes {A5='!', B5='\'', C5=0x10, D5=010, E5=- 0x10, F5=-010};
        typedef enum { Value0 = 0 } e_t, *pe_t;
        enum e_noninj { AA3=0, BB3=0, CC3=0, DD3=0 };
        enum e_prev { AA4, BB4=2, CC4=4, DD4=BB4, EE4, FF4=CC4, GG4=FF4 };

        struct nesting { struct abc d, e; };
        struct array2 { int a, b; int c[99]; };
        struct align { char a; short b; char c; };
        struct bitfield { int a:10, b:20, c:3; };
        typedef enum { AA2, BB2, CC2 } foo_e_t;
        typedef struct { foo_e_t f:2; } bfenum_t;
        typedef struct { int a; } anon_foo_t;
        typedef struct { char b, c; } anon_bar_t;
        typedef struct named_foo_s { int a; } named_foo_t, *named_foo_p;
        typedef struct { int a; } unnamed_foo_t, *unnamed_foo_p;
        struct nonpacked { char a; int b; };
        struct array0 { int len; short data[0]; };
        struct array_no_length { int x; int a[]; };

        struct nested_anon {
            struct { int a, b; };
            union { int c, d; };
        };
        struct nested_field_ofs_s {
            struct { int a; char b; };
            union { char c; };
        };
        union nested_anon_u {
            struct { int a, b; };
            union { int c, d; };
        };
        struct abc50 { int a, b; int c[50]; };
        struct ints_and_bitfield { int a,b,c,d,e; int x:1; };
    """
    DEFS_PACKED = """
        struct is_packed { char a; int b; } /*here*/;
    """
    if sys.platform == "win32":
        DEFS = DEFS.replace('data[0]', 'data[1]')   # not supported
        CCODE = (DEFS + "\n#pragma pack(push,1)\n" + DEFS_PACKED +
                 "\n#pragma pack(pop)\n")
    else:
        CCODE = (DEFS +
                 DEFS_PACKED.replace('/*here*/', '__attribute__((packed))'))

    ffi1.cdef(DEFS)
    ffi1.cdef(DEFS_PACKED, packed=True)
    ffi1.set_source("test_new_ffi_1", CCODE)

    outputfilename = recompile(ffi1, "test_new_ffi_1", CCODE,
                               tmpdir=str(udir))
    module = load_dynamic("test_new_ffi_1", outputfilename)
    ffi = module.ffi
    construction_params = (ffi1, CCODE)


class TestNewFFI1:

    def test_integer_ranges(self):
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
        e = pytest.raises(TypeError, ffi.new, "int")
        assert str(e.value) == "expected a pointer or array ctype, got 'int'"

    def test_new_single_integer(self):
        p = ffi.new("int *")     # similar to ffi.new("int[1]")
        assert p[0] == 0
        p[0] = -123
        assert p[0] == -123
        p = ffi.new("int *", -42)
        assert p[0] == -42
        assert repr(p) == "<cdata 'int *' owning %d bytes>" % SIZE_OF_INT

    def test_new_array_no_arg(self):
        p = ffi.new("int[10]")
        # the object was zero-initialized:
        for i in range(10):
            assert p[i] == 0

    def test_array_indexing(self):
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

    def test_new_array_args(self):
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
        n = ffi.new("int *", 24)
        a = ffi.new("int *[10]", [ffi.NULL, ffi.NULL, n, n, ffi.NULL])
        for i in range(10):
            if i not in (2, 3):
                assert a[i] == ffi.NULL
        assert a[2] == a[3] == n

    def test_cannot_cast(self):
        a = ffi.new("short int[10]")
        e = pytest.raises(TypeError, ffi.new, "long int **", a)
        msg = str(e.value)
        assert "'short[10]'" in msg and "'long *'" in msg

    def test_new_pointer_to_array(self):
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
        typerepr = "<ctype '%s'>"
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
        p = ffi.new("struct repr *")
        assert repr(p) == "<cdata 'struct repr *' owning %d bytes>" % (
            3*SIZE_OF_SHORT)
        assert repr(ffi.typeof(p)) == typerepr % "struct repr *"
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
        p = ffi.new("struct repr*")
        q = ffi.cast("struct repr *", p)
        assert repr(q).startswith("<cdata 'struct repr *' 0x")
        assert repr(ffi.typeof(q)) == typerepr % "struct repr *"
        prevrepr = repr(q)
        q = q[0]
        assert repr(q) == prevrepr.replace(' *', ' &')
        assert repr(ffi.typeof(q)) == typerepr % "struct repr"

    def test_new_array_of_array(self):
        p = ffi.new("int[3][4]")
        p[0][0] = 10
        p[2][3] = 33
        assert p[0][0] == 10
        assert p[2][3] == 33
        with pytest.raises(IndexError):
            p[1][-1]

    def test_constructor_array_of_array(self):
        p = ffi.new("int[3][2]", [[10, 11], [12, 13], [14, 15]])
        assert p[2][1] == 15

    def test_new_array_of_pointer_1(self):
        n = ffi.new("int*", 99)
        p = ffi.new("int*[4]")
        p[3] = n
        a = p[3]
        assert repr(a).startswith("<cdata 'int *' 0x")
        assert a[0] == 99

    def test_new_array_of_pointer_2(self):
        n = ffi.new("int[1]", [99])
        p = ffi.new("int*[4]")
        p[3] = n
        a = p[3]
        assert repr(a).startswith("<cdata 'int *' 0x")
        assert a[0] == 99

    def test_char(self):
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
        s = ffi.new("struct simple*")
        assert s.a == s.b == s.c == 0
        s.b = -23
        assert s.b == -23
        with pytest.raises(OverflowError):
            s.b = 32768
        #
        s = ffi.new("struct simple*", [-2, -3])
        assert s.a == -2
        assert s.b == -3
        assert s.c == 0
        with pytest.raises((AttributeError, TypeError)):
            del s.a
        assert repr(s) == "<cdata 'struct simple *' owning %d bytes>" % (
            SIZE_OF_INT + 2 * SIZE_OF_SHORT)
        #
        pytest.raises(ValueError, ffi.new, "struct simple*", [1, 2, 3, 4])

    def test_constructor_struct_from_dict(self):
        s = ffi.new("struct simple*", {'b': 123, 'c': 456})
        assert s.a == 0
        assert s.b == 123
        assert s.c == 456
        pytest.raises(KeyError, ffi.new, "struct simple*", {'d': 456})

    def test_struct_pointer(self):
        s = ffi.new("struct simple*")
        assert s[0].a == s[0].b == s[0].c == 0
        s[0].b = -23
        assert s[0].b == s.b == -23
        with pytest.raises(OverflowError):
            s[0].b = -32769
        with pytest.raises(IndexError):
            s[1]

    def test_struct_opaque(self):
        pytest.raises(ffi.error, ffi.new, "struct baz*")
        # should 'ffi.new("struct baz **") work?  it used to, but it was
        # not particularly useful...
        pytest.raises(ffi.error, ffi.new, "struct baz**")

    def test_pointer_to_struct(self):
        s = ffi.new("struct simple *")
        s.a = -42
        assert s[0].a == -42
        p = ffi.new("struct simple **", s)
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
        s = ffi.new("struct array *", [[10, 11], [b'a', b'b', b'c']])
        assert s.a[1] == 11
        assert s.b[2] == b'c'
        s.b[1] = b'X'
        assert s.b[0] == b'a'
        assert s.b[1] == b'X'
        assert s.b[2] == b'c'

    def test_recursive_struct(self):
        s = ffi.new("struct recursive*")
        t = ffi.new("struct recursive*")
        s.value = 123
        s.next = t
        t.value = 456
        assert s.value == 123
        assert s.next.value == 456

    def test_union_simple(self):
        u = ffi.new("union simple_u*")
        assert u.a == u.b == u.c == 0
        u.b = -23
        assert u.b == -23
        assert u.a != 0
        with pytest.raises(OverflowError):
            u.b = 32768
        #
        u = ffi.new("union simple_u*", [-2])
        assert u.a == -2
        with pytest.raises((AttributeError, TypeError)):
            del u.a
        assert repr(u) == "<cdata 'union simple_u *' owning %d bytes>" % (
            SIZE_OF_INT,)

    def test_union_opaque(self):
        pytest.raises(ffi.error, ffi.new, "union baz*")
        # should 'ffi.new("union baz **") work?  it used to, but it was
        # not particularly useful...
        pytest.raises(ffi.error, ffi.new, "union baz**")

    def test_union_initializer(self):
        pytest.raises(TypeError, ffi.new, "union init_u*", b'A')
        pytest.raises(TypeError, ffi.new, "union init_u*", 5)
        pytest.raises(ValueError, ffi.new, "union init_u*", [b'A', 5])
        u = ffi.new("union init_u*", [b'A'])
        assert u.a == b'A'
        pytest.raises(TypeError, ffi.new, "union init_u*", [1005])
        u = ffi.new("union init_u*", {'b': 12345})
        assert u.b == 12345
        u = ffi.new("union init_u*", [])
        assert u.a == b'\x00'
        assert u.b == 0

    def test_sizeof_type(self):
        for c_type, expected_size in [
            ('char', 1),
            ('unsigned int', 4),
            ('char *', SIZE_OF_PTR),
            ('int[5]', 20),
            ('struct four_s', 12),
            ('union four_u', 4),
            ]:
            size = ffi.sizeof(c_type)
            assert size == expected_size, (size, expected_size, ctype)

    def test_sizeof_cdata(self):
        assert ffi.sizeof(ffi.new("short*")) == SIZE_OF_PTR
        assert ffi.sizeof(ffi.cast("short", 123)) == SIZE_OF_SHORT
        #
        a = ffi.new("int[]", [10, 11, 12, 13, 14])
        assert len(a) == 5
        assert ffi.sizeof(a) == 5 * SIZE_OF_INT

    def test_string_from_char_pointer(self):
        x = ffi.new("char*", b"x")
        assert str(x) == repr(x)
        assert ffi.string(x) == b"x"
        assert ffi.string(ffi.new("char*", b"\x00")) == b""
        pytest.raises(TypeError, ffi.new, "char*", unicode("foo"))

    def test_unicode_from_wchar_pointer(self):
        self.check_wchar_t(ffi)
        x = ffi.new("wchar_t*", u+"x")
        assert unicode(x) == unicode(repr(x))
        assert ffi.string(x) == u+"x"
        assert ffi.string(ffi.new("wchar_t*", u+"\x00")) == u+""

    def test_string_from_char_array(self):
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
        # 'const' is ignored so far, in the declaration of 'struct string'
        t = ffi.new("const char[]", b"testing")
        s = ffi.new("struct string*", [t])
        assert type(s.name) not in (bytes, str, unicode)
        assert ffi.string(s.name) == b"testing"
        with pytest.raises(TypeError):
            s.name = None
        s.name = ffi.NULL
        assert s.name == ffi.NULL

    def test_fetch_const_wchar_p_field(self):
        # 'const' is ignored so far
        self.check_wchar_t(ffi)
        t = ffi.new("const wchar_t[]", u+"testing")
        s = ffi.new("struct ustring*", [t])
        assert type(s.name) not in (bytes, str, unicode)
        assert ffi.string(s.name) == u+"testing"
        s.name = ffi.NULL
        assert s.name == ffi.NULL

    def test_voidp(self):
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
        s = ffi.new("struct voidp *")
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
        t = ffi.typeof("int(*(*)(int))(int)")
        assert repr(t) == "<ctype '%s'>" % "int(*(*)(int))(int)"

    def test_functionptr_voidptr_return(self):
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
        def foo():
            pass
        foo_cb = ffi.callback("void foo()", foo)
        result = foo_cb()
        assert result is None

    def test_char_cast(self):
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
        a = ffi.new("short int[]", [0x1234, 0x5678])
        p = ffi.cast("char*", a)
        data = b''.join([p[i] for i in range(4)])
        if sys.byteorder == 'little':
            assert data == b'\x34\x12\x78\x56'
        else:
            assert data == b'\x12\x34\x56\x78'

    def test_cast_between_pointers(self):
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
        def cb(n):
            raise Exception
        a = ffi.callback("int(*)(int)", cb, error=42)
        res = a(1)    # and the error reported to stderr
        assert res == 42

    def test_structptr_argument(self):
        def cb(p):
            return p[0].a * 1000 + p[0].b * 100 + p[1].a * 10 + p[1].b
        a = ffi.callback("int(*)(struct ab[])", cb)
        res = a([[5, 6], {'a': 7, 'b': 8}])
        assert res == 5678
        res = a([[5], {'b': 8}])
        assert res == 5008

    def test_array_argument_as_list(self):
        seen = []
        def cb(argv):
            seen.append(ffi.string(argv[0]))
            seen.append(ffi.string(argv[1]))
        a = ffi.callback("void(*)(char *[])", cb)
        a([ffi.new("char[]", b"foobar"), ffi.new("char[]", b"baz")])
        assert seen == [b"foobar", b"baz"]

    def test_cast_float(self):
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
        # enum foq { A0, B0, CC0, D0 };
        assert ffi.string(ffi.cast("enum foq", 0)) == "cffiA0"
        assert ffi.string(ffi.cast("enum foq", 2)) == "cffiCC0"
        assert ffi.string(ffi.cast("enum foq", 3)) == "cffiD0"
        assert ffi.string(ffi.cast("enum foq", 4)) == "4"
        # enum bar { A1, B1=-2, CC1, D1, E1 };
        assert ffi.string(ffi.cast("enum bar", 0)) == "A1"
        assert ffi.string(ffi.cast("enum bar", -2)) == "B1"
        assert ffi.string(ffi.cast("enum bar", -1)) == "CC1"
        assert ffi.string(ffi.cast("enum bar", 1)) == "E1"
        assert ffi.cast("enum bar", -2) == ffi.cast("enum bar", -2)
        assert ffi.cast("enum foq", 0) == ffi.cast("enum bar", 0)
        assert ffi.cast("enum bar", 0) == ffi.cast("int", 0)
        assert repr(ffi.cast("enum bar", -1)) == "<cdata 'enum bar' -1: CC1>"
        assert repr(ffi.cast("enum foq", -1)) == (  # enums are unsigned, if
            "<cdata 'enum foq' 4294967295>") or (   # they contain no neg value
                sys.platform == "win32")            # (but not on msvc)
        # enum baz { A2=0x1000, B2=0x2000 };
        assert ffi.string(ffi.cast("enum baz", 0x1000)) == "A2"
        assert ffi.string(ffi.cast("enum baz", 0x2000)) == "B2"

    def test_enum_in_struct(self):
        # enum foo2 { A3, B3, C3, D3 };
        # struct bar_with_e { enum foo2 e; };
        s = ffi.new("struct bar_with_e *")
        s.e = 0
        assert s.e == 0
        s.e = 3
        assert s.e == 3
        assert s[0].e == 3
        s[0].e = 2
        assert s.e == 2
        assert s[0].e == 2
        s.e = ffi.cast("enum foo2", -1)
        assert s.e in (4294967295, -1)     # two choices
        assert s[0].e in (4294967295, -1)
        s.e = s.e
        with pytest.raises(TypeError):
            s.e = 'B3'
        with pytest.raises(TypeError):
            s.e = '2'
        with pytest.raises(TypeError):
            s.e = '#2'
        with pytest.raises(TypeError):
            s.e = '#7'

    def test_enum_non_contiguous(self):
        # enum noncont { A4, B4=42, C4 };
        assert ffi.string(ffi.cast("enum noncont", 0)) == "A4"
        assert ffi.string(ffi.cast("enum noncont", 42)) == "B4"
        assert ffi.string(ffi.cast("enum noncont", 43)) == "C4"
        invalid_value = ffi.cast("enum noncont", 2)
        assert int(invalid_value) == 2
        assert ffi.string(invalid_value) == "2"

    def test_enum_char_hex_oct(self):
        # enum etypes {A5='!', B5='\'', C5=0x10, D5=010, E5=- 0x10, F5=-010};
        assert ffi.string(ffi.cast("enum etypes", ord('!'))) == "A5"
        assert ffi.string(ffi.cast("enum etypes", ord("'"))) == "B5"
        assert ffi.string(ffi.cast("enum etypes", 16)) == "C5"
        assert ffi.string(ffi.cast("enum etypes", 8)) == "D5"
        assert ffi.string(ffi.cast("enum etypes", -16)) == "E5"
        assert ffi.string(ffi.cast("enum etypes", -8)) == "F5"

    def test_array_of_struct(self):
        s = ffi.new("struct ab[1]")
        with pytest.raises(AttributeError):
            s.b
        with pytest.raises(AttributeError):
            s.b = 412
        s[0].b = 412
        assert s[0].b == 412
        with pytest.raises(IndexError):
            s[1]

    def test_pointer_to_array(self):
        p = ffi.new("int(**)[5]")
        assert repr(p) == "<cdata 'int(* *)[5]' owning %d bytes>" % SIZE_OF_PTR

    def test_iterate_array(self):
        a = ffi.new("char[]", b"hello")
        assert list(a) == [b"h", b"e", b"l", b"l", b"o", b"\0"]
        assert list(iter(a)) == [b"h", b"e", b"l", b"l", b"o", b"\0"]
        #
        pytest.raises(TypeError, iter, ffi.cast("char *", a))
        pytest.raises(TypeError, list, ffi.cast("char *", a))
        pytest.raises(TypeError, iter, ffi.new("int *"))
        pytest.raises(TypeError, list, ffi.new("int *"))

    def test_offsetof(self):
        # struct abc { int a, b, c; };
        assert ffi.offsetof("struct abc", "a") == 0
        assert ffi.offsetof("struct abc", "b") == 4
        assert ffi.offsetof("struct abc", "c") == 8

    def test_offsetof_nested(self):
        # struct nesting { struct abc d, e; };
        assert ffi.offsetof("struct nesting", "e") == 12
        pytest.raises(KeyError, ffi.offsetof, "struct nesting", "e.a")
        assert ffi.offsetof("struct nesting", "e", "a") == 12
        assert ffi.offsetof("struct nesting", "e", "b") == 16
        assert ffi.offsetof("struct nesting", "e", "c") == 20

    def test_offsetof_array(self):
        assert ffi.offsetof("int[]", 51) == 51 * ffi.sizeof("int")
        assert ffi.offsetof("int *", 51) == 51 * ffi.sizeof("int")
        # struct array2 { int a, b; int c[99]; };
        assert ffi.offsetof("struct array2", "c") == 2 * ffi.sizeof("int")
        assert ffi.offsetof("struct array2", "c", 0) == 2 * ffi.sizeof("int")
        assert ffi.offsetof("struct array2", "c", 51) == 53 * ffi.sizeof("int")

    def test_alignof(self):
        # struct align { char a; short b; char c; };
        assert ffi.alignof("int") == 4
        assert ffi.alignof("double") in (4, 8)
        assert ffi.alignof("struct align") == 2

    def test_bitfield(self):
        # struct bitfield { int a:10, b:20, c:3; };
        assert ffi.sizeof("struct bitfield") == 8
        s = ffi.new("struct bitfield *")
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
        # typedef enum { AA1, BB1, CC1 } foo_e_t;
        # typedef struct { foo_e_t f:2; } bfenum_t;
        if sys.platform == "win32":
            pytest.skip("enums are not unsigned")
        s = ffi.new("bfenum_t *")
        s.f = 2
        assert s.f == 2

    def test_anonymous_struct(self):
        # typedef struct { int a; } anon_foo_t;
        # typedef struct { char b, c; } anon_bar_t;
        f = ffi.new("anon_foo_t *", [12345])
        b = ffi.new("anon_bar_t *", [b"B", b"C"])
        assert f.a == 12345
        assert b.b == b"B"
        assert b.c == b"C"
        assert repr(b).startswith("<cdata 'anon_bar_t *'")

    def test_struct_with_two_usages(self):
        # typedef struct named_foo_s { int a; } named_foo_t, *named_foo_p;
        # typedef struct { int a; } unnamed_foo_t, *unnamed_foo_p;
        f = ffi.new("named_foo_t *", [12345])
        ps = ffi.new("named_foo_p[]", [f])
        f = ffi.new("unnamed_foo_t *", [12345])
        ps = ffi.new("unnamed_foo_p[]", [f])

    def test_pointer_arithmetic(self):
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
        x = ffi.cast("int", 123)
        y = ffi.cast("int", 456)
        assert x < y
        #
        z = ffi.cast("double", 78.9)
        assert x > z
        assert y > z

    def test_ffi_buffer_ptr(self):
        a = ffi.new("short *", 100)
        try:
            b = ffi.buffer(a)
        except NotImplementedError as e:
            pytest.skip(str(e))
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
        a1 = ffi.new("int[]", list(range(100, 110)))
        a2 = ffi.new("int[]", list(range(100, 115)))
        try:
            ffi.buffer(a1)
        except NotImplementedError as e:
            pytest.skip(str(e))
        assert ffi.buffer(a1)[:] == ffi.buffer(a2, 4*10)[:]

    def test_ffi_buffer_with_file(self):
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

    def test_array_in_struct(self):
        # struct array { int a[2]; char b[3]; };
        p = ffi.new("struct array *")
        p.a[1] = 5
        assert p.a[1] == 5
        assert repr(p.a).startswith("<cdata 'int[2]' 0x")

    def test_struct_containing_array_varsize_workaround(self):
        if sys.platform == "win32":
            pytest.skip("array of length 0 not supported")
        # struct array0 { int len; short data[0]; };
        p = ffi.new("char[]", ffi.sizeof("struct array0") + 7 * SIZE_OF_SHORT)
        q = ffi.cast("struct array0 *", p)
        assert q.len == 0
        # 'q.data' gets not a 'short[0]', but just a 'short *' instead
        assert repr(q.data).startswith("<cdata 'short *' 0x")
        assert q.data[6] == 0
        q.data[6] = 15
        assert q.data[6] == 15

    def test_new_struct_containing_array_varsize(self):
        pytest.skip("later?")
        ffi.cdef("struct foo_s { int len; short data[]; };")
        p = ffi.new("struct foo_s *", 10)     # a single integer is the length
        assert p.len == 0
        assert p.data[9] == 0
        with pytest.raises(IndexError):
            p.data[10]

    def test_ffi_typeof_getcname(self):
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
        f = ffi.cast("int(*)(int)", 42)
        assert f != ffi.NULL
        pytest.raises(ffi.error, ffi.cast, "int(int)", 42)
        pytest.raises(ffi.error, ffi.new, "int([5])(int)")
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
        def cb(i, va_list):
            j = ffi.va_arg(va_list, "int")
            k = ffi.va_arg(va_list, "long long")
            return i * 2 + j * 3 + k * 5
        f = ffi.callback("long long cb(long i, ...)", cb)
        res = f(10, ffi.cast("int", 100), ffi.cast("long long", 1000))
        assert res == 20 + 300 + 5000

    def test_callback_decorator(self):
        #
        @ffi.callback("long(long, long)", error=42)
        def cb(a, b):
            return a - b
        #
        assert cb(-100, -10) == -90
        sz = ffi.sizeof("long")
        assert cb((1 << (sz*8-1)) - 1, -10) == 42

    def test_anonymous_enum(self):
        # typedef enum { Value0 = 0 } e_t, *pe_t;
        assert ffi.getctype("e_t*") == 'e_t *'
        assert ffi.getctype("pe_t") == 'e_t *'
        assert ffi.getctype("foo_e_t*") == 'foo_e_t *'

    def test_new_ctype(self):
        p = ffi.new("int *")
        pytest.raises(TypeError, ffi.new, p)
        p = ffi.new(ffi.typeof("int *"), 42)
        assert p[0] == 42

    def test_enum_with_non_injective_mapping(self):
        # enum e_noninj { AA3=0, BB3=0, CC3=0, DD3=0 };
        e = ffi.cast("enum e_noninj", 0)
        assert ffi.string(e) == "AA3"     # pick the first one arbitrarily

    def test_enum_refer_previous_enum_value(self):
        # enum e_prev { AA4, BB4=2, CC4=4, DD4=BB4, EE4, FF4=CC4, GG4=FF4 };
        assert ffi.string(ffi.cast("enum e_prev", 2)) == "BB4"
        assert ffi.string(ffi.cast("enum e_prev", 3)) == "EE4"
        assert ffi.sizeof("char[DD4]") == 2
        assert ffi.sizeof("char[EE4]") == 3
        assert ffi.sizeof("char[FF4]") == 4
        assert ffi.sizeof("char[GG4]") == 4

    def test_nested_anonymous_struct(self):
        # struct nested_anon {
        #     struct { int a, b; };
        #     union { int c, d; };
        # };
        assert ffi.sizeof("struct nested_anon") == 3 * SIZE_OF_INT
        p = ffi.new("struct nested_anon *", [1, 2, 3])
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
        p = ffi.new("struct nested_anon *", {'b': 12, 'd': 14})
        assert p.a == 0
        assert p.b == 12
        assert p.c == 14
        assert p.d == 14

    def test_nested_field_offset_align(self):
        # struct nested_field_ofs_s {
        #    struct { int a; char b; };
        #    union { char c; };
        # };
        assert ffi.offsetof("struct nested_field_ofs_s", "c") == 2 * SIZE_OF_INT
        assert ffi.sizeof("struct nested_field_ofs_s") == 3 * SIZE_OF_INT

    def test_nested_anonymous_union(self):
        # union nested_anon_u {
        #     struct { int a, b; };
        #     union { int c, d; };
        # };
        assert ffi.sizeof("union nested_anon_u") == 2 * SIZE_OF_INT
        p = ffi.new("union nested_anon_u *", [5])
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
        p = ffi.new("union nested_anon_u *", {'d': 14})
        assert p.a == 14
        assert p.b == 0
        assert p.c == 14
        assert p.d == 14
        p = ffi.new("union nested_anon_u *", {'b': 12})
        assert p.a == 0
        assert p.b == 12
        assert p.c == 0
        assert p.d == 0
        # we cannot specify several items in the dict, even though
        # in theory in this particular case it would make sense
        # to give both 'a' and 'b'

    def test_cast_to_array_type(self):
        p = ffi.new("int[4]", [-5])
        q = ffi.cast("int[3]", p)
        assert q[0] == -5
        assert repr(q).startswith("<cdata 'int[3]' 0x")

    def test_gc(self):
        p = ffi.new("int *", 123)
        seen = []
        def destructor(p1):
            assert p1 is p
            assert p1[0] == 123
            seen.append(1)
        q = ffi.gc(p, destructor=destructor)
        import gc; gc.collect()
        assert seen == []
        del q
        import gc; gc.collect(); gc.collect(); gc.collect()
        assert seen == [1]

    def test_gc_2(self):
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

    def test_release(self):
        p = ffi.new("int[]", 123)
        ffi.release(p)
        # here, reading p[0] might give garbage or segfault...
        ffi.release(p)   # no effect

    def test_release_new_allocator(self):
        seen = []
        def myalloc(size):
            seen.append(size)
            return ffi.new("char[]", b"X" * size)
        def myfree(raw):
            seen.append(raw)
        alloc2 = ffi.new_allocator(alloc=myalloc, free=myfree)
        p = alloc2("int[]", 15)
        assert seen == [15 * 4]
        ffi.release(p)
        assert seen == [15 * 4, p]
        ffi.release(p)    # no effect
        assert seen == [15 * 4, p]
        #
        del seen[:]
        p = alloc2("struct ab *")
        assert seen == [2 * 4]
        ffi.release(p)
        assert seen == [2 * 4, p]
        ffi.release(p)    # no effect
        assert seen == [2 * 4, p]

    def test_CData_CType(self):
        assert isinstance(ffi.cast("int", 0), ffi.CData)
        assert isinstance(ffi.new("int *"), ffi.CData)
        assert not isinstance(ffi.typeof("int"), ffi.CData)
        assert not isinstance(ffi.cast("int", 0), ffi.CType)
        assert not isinstance(ffi.new("int *"), ffi.CType)

    def test_CData_CType_2(self):
        assert isinstance(ffi.typeof("int"), ffi.CType)

    def test_bool(self):
        assert int(ffi.cast("_Bool", 0.1)) == 1
        assert int(ffi.cast("_Bool", -0.0)) == 0
        assert int(ffi.cast("_Bool", b'\x02')) == 1
        assert int(ffi.cast("_Bool", b'\x00')) == 0
        assert int(ffi.cast("_Bool", b'\x80')) == 1
        assert ffi.new("_Bool *", False)[0] == 0
        assert ffi.new("_Bool *", 1)[0] == 1
        pytest.raises(OverflowError, ffi.new, "_Bool *", 2)
        pytest.raises(TypeError, ffi.string, ffi.cast("_Bool", 2))

    def test_addressof(self):
        p = ffi.new("struct ab *")
        a = ffi.addressof(p[0])
        assert repr(a).startswith("<cdata 'struct ab *' 0x")
        assert a == p
        pytest.raises(TypeError, ffi.addressof, p)
        pytest.raises((AttributeError, TypeError), ffi.addressof, 5)
        pytest.raises(TypeError, ffi.addressof, ffi.cast("int", 5))

    def test_addressof_field(self):
        p = ffi.new("struct ab *")
        b = ffi.addressof(p[0], 'b')
        assert repr(b).startswith("<cdata 'int *' 0x")
        assert int(ffi.cast("uintptr_t", b)) == (
            int(ffi.cast("uintptr_t", p)) + ffi.sizeof("int"))
        assert b == ffi.addressof(p, 'b')
        assert b != ffi.addressof(p, 'a')

    def test_addressof_field_nested(self):
        # struct nesting { struct abc d, e; };
        p = ffi.new("struct nesting *")
        pytest.raises(KeyError, ffi.addressof, p[0], 'e.b')
        a = ffi.addressof(p[0], 'e', 'b')
        assert int(ffi.cast("uintptr_t", a)) == (
            int(ffi.cast("uintptr_t", p)) +
            ffi.sizeof("struct abc") + ffi.sizeof("int"))

    def test_addressof_anonymous_struct(self):
        # typedef struct { int a; } anon_foo_t;
        p = ffi.new("anon_foo_t *")
        a = ffi.addressof(p[0])
        assert a == p

    def test_addressof_array(self):
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
        array = ffi.new("int[50]")
        p = ffi.cast("int *", array)
        pytest.raises(TypeError, ffi.addressof, p)
        assert ffi.addressof(p, 0) == p
        assert ffi.addressof(p, 25) == p + 25
        assert ffi.typeof(ffi.addressof(p, 25)) == ffi.typeof(p)
        #
        array = ffi.new("struct ab[50]")
        p = ffi.cast("int *", array)
        pytest.raises(TypeError, ffi.addressof, p)
        assert ffi.addressof(p, 0) == p
        assert ffi.addressof(p, 25) == p + 25
        assert ffi.typeof(ffi.addressof(p, 25)) == ffi.typeof(p)

    def test_addressof_array_in_struct(self):
        # struct abc50 { int a, b; int c[50]; };
        p = ffi.new("struct abc50 *")
        p1 = ffi.addressof(p, "c", 25)
        assert ffi.typeof(p1) is ffi.typeof("int *")
        assert p1 == ffi.cast("int *", p) + 27
        assert ffi.addressof(p, "c") == ffi.cast("int *", p) + 2
        assert ffi.addressof(p, "c", 0) == ffi.cast("int *", p) + 2
        p2 = ffi.addressof(p, 1)
        assert ffi.typeof(p2) is ffi.typeof("struct abc50 *")
        assert p2 == p + 1

    @pytest.mark.thread_unsafe(reason="workers would share a compilation directory")
    def test_multiple_independent_structs(self):
        CDEF2 = "struct ab { int x; };"
        ffi2 = cffi.FFI(); ffi2.cdef(CDEF2)
        outputfilename = recompile(ffi2, "test_multiple_independent_structs",
                                   CDEF2, tmpdir=str(udir))
        module = load_dynamic("test_multiple_independent_structs",
                                  outputfilename)
        ffi1 = module.ffi
        foo1 = ffi1.new("struct ab *", [10])
        foo2 = ffi .new("struct ab *", [20, 30])
        assert foo1.x == 10
        assert foo2.a == 20
        assert foo2.b == 30

    @pytest.mark.thread_unsafe(reason="workers would share a compilation directory")
    def test_include_struct_union_enum_typedef(self):
        ffi1, CCODE = construction_params
        ffi2 = cffi.FFI()
        ffi2.include(ffi1)
        outputfilename = recompile(ffi2,
                                   "test_include_struct_union_enum_typedef",
                                   CCODE, tmpdir=str(udir))
        module = load_dynamic("test_include_struct_union_enum_typedef",
                                  outputfilename)
        ffi2 = module.ffi
        #
        p = ffi2.new("struct nonpacked *", [b'A', -43141])
        assert p.a == b'A'
        assert p.b == -43141
        #
        p = ffi.new("union simple_u *", [-52525])
        assert p.a == -52525
        #
        p = ffi.cast("enum foq", 2)
        assert ffi.string(p) == "cffiCC0"
        assert ffi2.sizeof("char[cffiCC0]") == 2
        #
        p = ffi.new("anon_foo_t *", [-52526])
        assert p.a == -52526
        p = ffi.new("named_foo_p", [-52527])
        assert p.a == -52527

    def test_struct_packed(self):
        # struct nonpacked { char a; int b; };
        # struct is_packed { char a; int b; } __attribute__((packed));
        assert ffi.sizeof("struct nonpacked") == 8
        assert ffi.sizeof("struct is_packed") == 5
        assert ffi.alignof("struct nonpacked") == 4
        assert ffi.alignof("struct is_packed") == 1
        s = ffi.new("struct is_packed[2]")
        s[0].b = 42623381
        s[0].a = b'X'
        s[1].b = -4892220
        s[1].a = b'Y'
        assert s[0].b == 42623381
        assert s[0].a == b'X'
        assert s[1].b == -4892220
        assert s[1].a == b'Y'

    def test_not_supported_bitfield_in_result(self):
        # struct ints_and_bitfield { int a,b,c,d,e; int x:1; };
        e = pytest.raises(NotImplementedError, ffi.callback,
                           "struct ints_and_bitfield foo(void)", lambda: 42)
        assert str(e.value) == ("struct ints_and_bitfield(*)(): "
            "callback with unsupported argument or return type or with '...'")

    def test_inspecttype(self):
        assert ffi.typeof("long").kind == "primitive"
        assert ffi.typeof("long(*)(long, long**, ...)").cname == (
            "long(*)(long, long * *, ...)")
        assert ffi.typeof("long(*)(long, long**, ...)").ellipsis is True

    def test_new_handle(self):
        o = [2, 3, 4]
        p = ffi.new_handle(o)
        assert ffi.typeof(p) == ffi.typeof("void *")
        assert ffi.from_handle(p) is o
        assert ffi.from_handle(ffi.cast("char *", p)) is o
        pytest.raises(RuntimeError, ffi.from_handle, ffi.NULL)

    def test_struct_array_no_length(self):
        # struct array_no_length { int x; int a[]; };
        p = ffi.new("struct array_no_length *", [100, [200, 300, 400]])
        assert p.x == 100
        assert ffi.typeof(p.a) is ffi.typeof("int[]")   # length available
        assert p.a[0] == 200
        assert p.a[1] == 300
        assert p.a[2] == 400
        assert len(p.a) == 3
        assert list(p.a) == [200, 300, 400]
        q = ffi.cast("struct array_no_length *", p)
        assert ffi.typeof(q.a) is ffi.typeof("int *")   # no length available
        assert q.a[0] == 200
        assert q.a[1] == 300
        assert q.a[2] == 400
        pytest.raises(TypeError, len, q.a)
        pytest.raises(TypeError, list, q.a)

    def test_all_primitives(self):
        assert set(PRIMITIVE_TO_INDEX) == set([
            "char",
            "short",
            "int",
            "long",
            "long long",
            "signed char",
            "unsigned char",
            "unsigned short",
            "unsigned int",
            "unsigned long",
            "unsigned long long",
            "float",
            "double",
            "long double",
            "wchar_t",
            "char16_t",
            "char32_t",
            "_Bool",
            "int8_t",
            "uint8_t",
            "int16_t",
            "uint16_t",
            "int32_t",
            "uint32_t",
            "int64_t",
            "uint64_t",
            "int_least8_t",
            "uint_least8_t",
            "int_least16_t",
            "uint_least16_t",
            "int_least32_t",
            "uint_least32_t",
            "int_least64_t",
            "uint_least64_t",
            "int_fast8_t",
            "uint_fast8_t",
            "int_fast16_t",
            "uint_fast16_t",
            "int_fast32_t",
            "uint_fast32_t",
            "int_fast64_t",
            "uint_fast64_t",
            "intptr_t",
            "uintptr_t",
            "intmax_t",
            "uintmax_t",
            "ptrdiff_t",
            "size_t",
            "ssize_t",
            '_cffi_float_complex_t',
            '_cffi_double_complex_t',
            ])
        for name in PRIMITIVE_TO_INDEX:
            x = ffi.sizeof(name)
            assert 1 <= x <= 16

    @pytest.mark.thread_unsafe(reason="workers would share a compilation directory")
    def test_emit_c_code(self):
        ffi = cffi.FFI()
        ffi.set_source("foobar", "??")
        c_file = str(udir.join('test_emit_c_code'))
        ffi.emit_c_code(c_file)
        assert os.path.isfile(c_file)

    @pytest.mark.thread_unsafe(reason="workers would share a compilation directory")
    def test_emit_c_code_to_file_obj(self):
        ffi = cffi.FFI()
        ffi.set_source("foobar", "??")
        fileobj = NativeIO()
        ffi.emit_c_code(fileobj)
        assert 'foobar' in fileobj.getvalue()

    @pytest.mark.thread_unsafe(reason="workers would share a compilation directory")
    def test_import_from_lib(self):
        ffi2 = cffi.FFI()
        ffi2.cdef("int myfunc(int); extern int myvar;\n#define MYFOO ...\n")
        outputfilename = recompile(ffi2, "_test_import_from_lib",
                                   "int myfunc(int x) { return x + 1; }\n"
                                   "int myvar = -5;\n"
                                   "#define MYFOO 42", tmpdir=str(udir))
        load_dynamic("_test_import_from_lib", outputfilename)
        from _test_import_from_lib.lib import myfunc, myvar, MYFOO
        assert MYFOO == 42
        assert myfunc(43) == 44
        assert myvar == -5     # but can't be changed, so not very useful
        with pytest.raises(ImportError):
            from _test_import_from_lib.lib import bar
        d = {}
        exec("from _test_import_from_lib.lib import *", d)
        assert (set(key for key in d if not key.startswith('_')) ==
                set(['myfunc', 'MYFOO']))
        #
        # also test "import *" on the module itself, which should be
        # equivalent to "import ffi, lib"
        d = {}
        exec("from _test_import_from_lib import *", d)
        assert (sorted([x for x in d.keys() if not x.startswith('__')]) ==
                ['ffi', 'lib'])

    def test_char16_t(self):
        x = ffi.new("char16_t[]", 5)
        assert len(x) == 5 and ffi.sizeof(x) == 10
        x[2] = u+'\u1324'
        assert x[2] == u+'\u1324'
        y = ffi.new("char16_t[]", u+'\u1234\u5678')
        assert len(y) == 3
        assert list(y) == [u+'\u1234', u+'\u5678', u+'\x00']
        assert ffi.string(y) == u+'\u1234\u5678'
        z = ffi.new("char16_t[]", u+'\U00012345')
        assert len(z) == 3
        assert list(z) == [u+'\ud808', u+'\udf45', u+'\x00']
        assert ffi.string(z) == u+'\U00012345'

    def test_char32_t(self):
        x = ffi.new("char32_t[]", 5)
        assert len(x) == 5 and ffi.sizeof(x) == 20
        x[3] = u+'\U00013245'
        assert x[3] == u+'\U00013245'
        y = ffi.new("char32_t[]", u+'\u1234\u5678')
        assert len(y) == 3
        assert list(y) == [u+'\u1234', u+'\u5678', u+'\x00']
        z = ffi.new("char32_t[]", u+'\U00012345')
        assert len(z) == 2
        assert list(z) == [u+'\U00012345', u+'\x00'] # maybe a 2-unichars string
        assert ffi.string(z) == u+'\U00012345'
