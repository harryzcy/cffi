import sys, platform
import pytest
from testing.cffi0 import backend_tests, test_function, test_ownlib
from testing.support import u
from cffi import FFI
import _cffi_backend


class TestFFI(backend_tests.BackendTests,
              test_function.TestFunction,
              test_ownlib.TestOwnLib):
    TypeRepr = "<ctype '%s'>"

    @staticmethod
    def Backend():
        return _cffi_backend

    def test_not_supported_bitfield_in_result(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo_s { int a,b,c,d,e; int x:1; };")
        e = pytest.raises(NotImplementedError, ffi.callback,
                           "struct foo_s foo(void)", lambda: 42)
        assert str(e.value) == ("struct foo_s(*)(): "
            "callback with unsupported argument or return type or with '...'")

    def test_inspecttype(self):
        ffi = FFI(backend=self.Backend())
        assert ffi.typeof("long").kind == "primitive"
        assert ffi.typeof("long(*)(long, long**, ...)").cname == (
            "long(*)(long, long * *, ...)")
        assert ffi.typeof("long(*)(long, long**, ...)").ellipsis is True

    def test_new_handle(self):
        ffi = FFI(backend=self.Backend())
        o = [2, 3, 4]
        p = ffi.new_handle(o)
        assert ffi.typeof(p) == ffi.typeof("void *")
        assert ffi.from_handle(p) is o
        assert ffi.from_handle(ffi.cast("char *", p)) is o
        pytest.raises(RuntimeError, ffi.from_handle, ffi.NULL)

    def test_callback_onerror(self):
        ffi = FFI(backend=self.Backend())
        seen = []
        def oops(*args):
            seen.append(args)
        def otherfunc():
            raise LookupError
        def cb(n):
            otherfunc()
        a = ffi.callback("int(*)(int)", cb, error=42, onerror=oops)
        res = a(234)
        assert res == 42
        assert len(seen) == 1
        exc, val, tb = seen[0]
        assert exc is LookupError
        assert isinstance(val, LookupError)
        assert tb.tb_frame.f_code.co_name == 'cb'
        assert tb.tb_frame.f_locals['n'] == 234

    def test_ffi_new_allocator_2(self):
        ffi = FFI(backend=self.Backend())
        seen = []
        def myalloc(size):
            seen.append(size)
            return ffi.new("char[]", b"X" * size)
        def myfree(raw):
            seen.append(raw)
        alloc1 = ffi.new_allocator(myalloc, myfree)
        alloc2 = ffi.new_allocator(alloc=myalloc, free=myfree,
                                   should_clear_after_alloc=False)
        p1 = alloc1("int[10]")
        p2 = alloc2("int[]", 10)
        assert seen == [40, 40]
        assert ffi.typeof(p1) == ffi.typeof("int[10]")
        assert ffi.sizeof(p1) == 40
        assert ffi.typeof(p2) == ffi.typeof("int[]")
        assert ffi.sizeof(p2) == 40
        assert p1[5] == 0
        assert p2[6] == ord('X') * 0x01010101
        raw1 = ffi.cast("char *", p1)
        raw2 = ffi.cast("char *", p2)
        del p1, p2
        retries = 0
        while len(seen) != 4:
            retries += 1
            assert retries <= 5
            import gc; gc.collect()
        assert seen == [40, 40, raw1, raw2]
        assert repr(seen[2]) == "<cdata 'char[]' owning 41 bytes>"
        assert repr(seen[3]) == "<cdata 'char[]' owning 41 bytes>"

    def test_ffi_new_allocator_3(self):
        ffi = FFI(backend=self.Backend())
        seen = []
        def myalloc(size):
            seen.append(size)
            return ffi.new("char[]", b"X" * size)
        alloc1 = ffi.new_allocator(myalloc)    # no 'free'
        p1 = alloc1("int[10]")
        assert seen == [40]
        assert ffi.typeof(p1) == ffi.typeof("int[10]")
        assert ffi.sizeof(p1) == 40
        assert p1[5] == 0

    def test_ffi_new_allocator_4(self):
        ffi = FFI(backend=self.Backend())
        pytest.raises(TypeError, ffi.new_allocator, free=lambda x: None)
        #
        def myalloc2(size):
            raise LookupError
        alloc2 = ffi.new_allocator(myalloc2)
        pytest.raises(LookupError, alloc2, "int[5]")
        #
        def myalloc3(size):
            return 42
        alloc3 = ffi.new_allocator(myalloc3)
        e = pytest.raises(TypeError, alloc3, "int[5]")
        assert str(e.value) == "alloc() must return a cdata object (got int)"
        #
        def myalloc4(size):
            return ffi.cast("int", 42)
        alloc4 = ffi.new_allocator(myalloc4)
        e = pytest.raises(TypeError, alloc4, "int[5]")
        assert str(e.value) == "alloc() must return a cdata pointer, not 'int'"
        #
        def myalloc5(size):
            return ffi.NULL
        alloc5 = ffi.new_allocator(myalloc5)
        pytest.raises(MemoryError, alloc5, "int[5]")

    def test_new_struct_containing_struct_containing_array_varsize(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            struct foo_s { int len[100]; short data[]; };
            struct bar_s { int abc[100]; struct foo_s tail; };
        """)
        # loop to try to detect heap overwrites, if the size allocated
        # is too small
        for i in range(1, 501, 100):
            p = ffi.new("struct bar_s *", [[10], [[20], [3,4,5,6,7,8,9] * i]])
            assert p.abc[0] == 10
            assert p.tail.len[0] == 20
            assert p.tail.data[0] == 3
            assert p.tail.data[6] == 9
            assert p.tail.data[7 * i - 1] == 9

    def test_bogus_struct_containing_struct_containing_array_varsize(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            struct foo_s { signed char len; signed char data[]; };
            struct bar_s { struct foo_s foo; int bcd; };
        """)
        p = ffi.new("struct bar_s *", [[123, [45, 56, 67, 78]], 9999999])
        assert p.foo.len == 123
        assert p.foo.data[0] == 45
        assert p.foo.data[1] == 56
        assert p.foo.data[2] == 67
        assert p.bcd == 9999999
        assert p.foo.data[3] != 78   # has been overwritten with 9999999

    def test_issue553(self):
        import gc, warnings
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int *", 123)
        with warnings.catch_warnings(record=True) as w:
            ffi.gc(p, lambda x: None)
            gc.collect()
        assert w == []

    def test_issue553_from_buffer(self):
        import gc, warnings
        ffi = FFI(backend=self.Backend())
        buf = b"123"
        with warnings.catch_warnings(record=True) as w:
            ffi.from_buffer(buf)
            gc.collect()
        assert w == []


class TestBitfield:
    def check(self, source, expected_ofs_y, expected_align, expected_size):
        # NOTE: 'expected_*' is the numbers expected from GCC.
        # The numbers expected from MSVC are not explicitly written
        # in this file, and will just be taken from the compiler.
        ffi = FFI()
        ffi.cdef("struct s1 { %s };" % source)
        ctype = ffi.typeof("struct s1")
        # verify the information with gcc
        ffi1 = FFI()
        ffi1.cdef("""
            static const int Gofs_y, Galign, Gsize;
            struct s1 *try_with_value(int fieldnum, long long value);
        """)
        fnames = [name for name, cfield in ctype.fields
                       if name and cfield.bitsize > 0]
        setters = ['case %d: s.%s = value; break;' % iname
                   for iname in enumerate(fnames)]
        lib = ffi1.verify("""
            #include <string.h>
            struct s1 { %s };
            struct sa { char a; struct s1 b; };
            #define Gofs_y  offsetof(struct s1, y)
            #define Galign  offsetof(struct sa, b)
            #define Gsize   sizeof(struct s1)
            struct s1 *try_with_value(int fieldnum, long long value)
            {
                static struct s1 s;
                memset(&s, 0, sizeof(s));
                switch (fieldnum) { %s }
                return &s;
            }
        """ % (source, ' '.join(setters)))
        if sys.platform == 'win32':
            expected_ofs_y = lib.Gofs_y
            expected_align = lib.Galign
            expected_size  = lib.Gsize
        else:
            assert (lib.Gofs_y, lib.Galign, lib.Gsize) == (
                expected_ofs_y, expected_align, expected_size)
        # the real test follows
        assert ffi.offsetof("struct s1", "y") == expected_ofs_y
        assert ffi.alignof("struct s1") == expected_align
        assert ffi.sizeof("struct s1") == expected_size
        # compare the actual storage of the two
        for name, cfield in ctype.fields:
            if cfield.bitsize < 0 or not name:
                continue
            if int(ffi.cast(cfield.type, -1)) == -1:   # signed
                min_value = -(1 << (cfield.bitsize-1))
                max_value = (1 << (cfield.bitsize-1)) - 1
            else:
                min_value = 0
                max_value = (1 << cfield.bitsize) - 1
            for t in [1, 2, 4, 8, 16, 128, 2813, 89728, 981729,
                     -1,-2,-4,-8,-16,-128,-2813,-89728,-981729]:
                if min_value <= t <= max_value:
                    self._fieldcheck(ffi, lib, fnames, name, t)

    def _fieldcheck(self, ffi, lib, fnames, name, value):
        s = ffi.new("struct s1 *")
        setattr(s, name, value)
        assert getattr(s, name) == value
        raw1 = ffi.buffer(s)[:]
        buff1 = ffi.buffer(s)
        t = lib.try_with_value(fnames.index(name), value)
        raw2 = ffi.buffer(t, len(raw1))[:]
        assert raw1 == raw2
        buff2 = ffi.buffer(t, len(buff1))
        assert buff1 == buff2

    @pytest.mark.thread_unsafe(reason="FFI verifier is not thread-safe")
    def test_bitfield_basic(self):
        self.check("int a; int b:9; int c:20; int y;", 8, 4, 12)
        self.check("int a; short b:9; short c:7; int y;", 8, 4, 12)
        self.check("int a; short b:9; short c:9; int y;", 8, 4, 12)

    @pytest.mark.thread_unsafe(reason="FFI verifier is not thread-safe")
    def test_bitfield_reuse_if_enough_space(self):
        self.check("int a:2; char y;", 1, 4, 4)
        self.check("int a:1; char b  ; int c:1; char y;", 3, 4, 4)
        self.check("int a:1; char b:8; int c:1; char y;", 3, 4, 4)
        self.check("char a; int b:9; char y;", 3, 4, 4)
        self.check("char a; short b:9; char y;", 4, 2, 6)
        self.check("int a:2; char b:6; char y;", 1, 4, 4)
        self.check("int a:2; char b:7; char y;", 2, 4, 4)
        self.check("int a:2; short b:15; char c:2; char y;", 5, 4, 8)
        self.check("int a:2; char b:1; char c:1; char y;", 1, 4, 4)

    @pytest.mark.skipif(
        "not (sys.platform == 'darwin' and platform.machine() == 'arm64')"
        " and "
        "platform.machine().startswith(('arm', 'aarch64'))")
    @pytest.mark.thread_unsafe(reason="FFI verifier is not thread-safe")
    def test_bitfield_anonymous_no_align(self):
        L = FFI().alignof("long long")
        self.check("char y; int :1;", 0, 1, 2)
        self.check("char x; int z:1; char y;", 2, 4, 4)
        self.check("char x; int  :1; char y;", 2, 1, 3)
        self.check("char x; long long z:48; char y;", 7, L, 8)
        self.check("char x; long long  :48; char y;", 7, 1, 8)
        self.check("char x; long long z:56; char y;", 8, L, 8 + L)
        self.check("char x; long long  :56; char y;", 8, 1, 9)
        self.check("char x; long long z:57; char y;", L + 8, L, L + 8 + L)
        self.check("char x; long long  :57; char y;", L + 8, 1, L + 9)

    @pytest.mark.skipif(
        "(sys.platform == 'darwin' and platform.machine() == 'arm64')"
        " or "
        "not platform.machine().startswith(('arm', 'aarch64'))")
    @pytest.mark.thread_unsafe(reason="FFI verifier is not thread-safe")
    def test_bitfield_anonymous_align_arm(self):
        L = FFI().alignof("long long")
        self.check("char y; int :1;", 0, 4, 4)
        self.check("char x; int z:1; char y;", 2, 4, 4)
        self.check("char x; int  :1; char y;", 2, 4, 4)
        self.check("char x; long long z:48; char y;", 7, L, 8)
        self.check("char x; long long  :48; char y;", 7, 8, 8)
        self.check("char x; long long z:56; char y;", 8, L, 8 + L)
        self.check("char x; long long  :56; char y;", 8, L, 8 + L)
        self.check("char x; long long z:57; char y;", L + 8, L, L + 8 + L)
        self.check("char x; long long  :57; char y;", L + 8, L, L + 8 + L)

    @pytest.mark.skipif(
        "not (sys.platform == 'darwin' and platform.machine() == 'arm64')"
        " and "
        "platform.machine().startswith(('arm', 'aarch64'))")
    @pytest.mark.thread_unsafe(reason="FFI verifier is not thread-safe")
    def test_bitfield_zero(self):
        L = FFI().alignof("long long")
        self.check("char y; int :0;", 0, 1, 4)
        self.check("char x; int :0; char y;", 4, 1, 5)
        self.check("char x; int :0; int :0; char y;", 4, 1, 5)
        self.check("char x; long long :0; char y;", L, 1, L + 1)
        self.check("short x, y; int :0; int :0;", 2, 2, 4)
        self.check("char x; int :0; short b:1; char y;", 5, 2, 6)
        self.check("int a:1; int :0; int b:1; char y;", 5, 4, 8)

    @pytest.mark.skipif(
        "(sys.platform == 'darwin' and platform.machine() == 'arm64')"
        " or "
        "not platform.machine().startswith(('arm', 'aarch64'))")
    @pytest.mark.thread_unsafe(reason="FFI verifier is not thread-safe")
    def test_bitfield_zero_arm(self):
        L = FFI().alignof("long long")
        self.check("char y; int :0;", 0, 4, 4)
        self.check("char x; int :0; char y;", 4, 4, 8)
        self.check("char x; int :0; int :0; char y;", 4, 4, 8)
        self.check("char x; long long :0; char y;", L, 8, L + 8)
        self.check("short x, y; int :0; int :0;", 2, 4, 4)
        self.check("char x; int :0; short b:1; char y;", 5, 4, 8)
        self.check("int a:1; int :0; int b:1; char y;", 5, 4, 8)

    def test_error_cases(self):
        ffi = FFI()
        ffi.cdef("struct s1 { float x:1; };")
        with pytest.raises(TypeError):
            ffi.new("struct s1 *")
        ffi.cdef("struct s2 { char x:0; };")
        with pytest.raises(TypeError):
            ffi.new("struct s2 *")
        ffi.cdef("struct s3 { char x:9; };")
        with pytest.raises(TypeError):
            ffi.new("struct s3 *")

    def test_struct_with_typedef(self):
        ffi = FFI()
        ffi.cdef("typedef struct { float x; } foo_t;")
        p = ffi.new("foo_t *", [5.2])
        assert repr(p).startswith("<cdata 'foo_t *' ")

    def test_struct_array_no_length(self):
        ffi = FFI()
        ffi.cdef("struct foo_s { int x; int a[]; };")
        p = ffi.new("struct foo_s *", [100, [200, 300, 400]])
        assert p.x == 100
        assert ffi.typeof(p.a) is ffi.typeof("int[]")
        assert len(p.a) == 3                            # length recorded
        assert p.a[0] == 200
        assert p.a[1] == 300
        assert p.a[2] == 400
        assert list(p.a) == [200, 300, 400]
        q = ffi.cast("struct foo_s *", p)
        assert q.x == 100
        assert ffi.typeof(q.a) is ffi.typeof("int *")   # no length recorded
        pytest.raises(TypeError, len, q.a)
        assert q.a[0] == 200
        assert q.a[1] == 300
        assert q.a[2] == 400
        pytest.raises(TypeError, list, q.a)

    @pytest.mark.skipif("sys.platform != 'win32'")
    def test_getwinerror(self):
        ffi = FFI()
        code, message = ffi.getwinerror(1155)
        assert code == 1155
        assert message == ("No application is associated with the "
                           "specified file for this operation")
        ffi.cdef("void SetLastError(int);")
        lib = ffi.dlopen("Kernel32.dll")
        lib.SetLastError(2)
        code, message = ffi.getwinerror()
        assert code == 2
        assert message == "The system cannot find the file specified"
        code, message = ffi.getwinerror(-1)
        assert code == 2
        assert message == "The system cannot find the file specified"

    def test_from_buffer(self):
        import array
        ffi = FFI()
        a = array.array('H', [10000, 20000, 30000])
        c = ffi.from_buffer(a)
        assert ffi.typeof(c) is ffi.typeof("char[]")
        assert len(c) == 6
        ffi.cast("unsigned short *", c)[1] += 500
        assert list(a) == [10000, 20500, 30000]
        assert c == ffi.from_buffer("char[]", a, True)
        assert c == ffi.from_buffer(a, require_writable=True)
        #
        c = ffi.from_buffer("unsigned short[]", a)
        assert len(c) == 3
        assert c[1] == 20500
        #
        p = ffi.from_buffer(b"abcd")
        assert p[2] == b"c"
        #
        assert p == ffi.from_buffer(b"abcd", require_writable=False)
        pytest.raises((TypeError, BufferError), ffi.from_buffer,
                                                 "char[]", b"abcd", True)
        pytest.raises((TypeError, BufferError), ffi.from_buffer, b"abcd",
                                                 require_writable=True)

    def test_release(self):
        ffi = FFI()
        p = ffi.new("int[]", 123)
        ffi.release(p)
        # here, reading p[0] might give garbage or segfault...
        ffi.release(p)   # no effect

    def test_memmove(self):
        ffi = FFI()
        p = ffi.new("short[]", [-1234, -2345, -3456, -4567, -5678])
        ffi.memmove(p, p + 1, 4)
        assert list(p) == [-2345, -3456, -3456, -4567, -5678]
        p[2] = 999
        ffi.memmove(p + 2, p, 6)
        assert list(p) == [-2345, -3456, -2345, -3456, 999]
        ffi.memmove(p + 4, ffi.new("char[]", b"\x71\x72"), 2)
        if sys.byteorder == 'little':
            assert list(p) == [-2345, -3456, -2345, -3456, 0x7271]
        else:
            assert list(p) == [-2345, -3456, -2345, -3456, 0x7172]

    def test_memmove_buffer(self):
        import array
        ffi = FFI()
        a = array.array('H', [10000, 20000, 30000])
        p = ffi.new("short[]", 5)
        ffi.memmove(p, a, 6)
        assert list(p) == [10000, 20000, 30000, 0, 0]
        ffi.memmove(p + 1, a, 6)
        assert list(p) == [10000, 10000, 20000, 30000, 0]
        b = array.array('h', [-1000, -2000, -3000])
        ffi.memmove(b, a, 4)
        assert b.tolist() == [10000, 20000, -3000]
        assert a.tolist() == [10000, 20000, 30000]
        p[0] = 999
        p[1] = 998
        p[2] = 997
        p[3] = 996
        p[4] = 995
        ffi.memmove(b, p, 2)
        assert b.tolist() == [999, 20000, -3000]
        ffi.memmove(b, p + 2, 4)
        assert b.tolist() == [997, 996, -3000]
        p[2] = -p[2]
        p[3] = -p[3]
        ffi.memmove(b, p + 2, 6)
        assert b.tolist() == [-997, -996, 995]

    def test_memmove_readonly_readwrite(self):
        ffi = FFI()
        p = ffi.new("signed char[]", 5)
        ffi.memmove(p, b"abcde", 3)
        assert list(p) == [ord("a"), ord("b"), ord("c"), 0, 0]
        ffi.memmove(p, bytearray(b"ABCDE"), 2)
        assert list(p) == [ord("A"), ord("B"), ord("c"), 0, 0]
        pytest.raises((TypeError, BufferError), ffi.memmove, b"abcde", p, 3)
        ba = bytearray(b"xxxxx")
        ffi.memmove(dest=ba, src=p, n=3)
        assert ba == bytearray(b"ABcxx")

    def test_all_primitives(self):
        ffi = FFI()
        for name in [
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
            ]:
            x = ffi.sizeof(name)
            assert 1 <= x <= 16

    def test_ffi_def_extern(self):
        ffi = FFI()
        pytest.raises(ValueError, ffi.def_extern)

    def test_introspect_typedef(self):
        ffi = FFI()
        ffi.cdef("typedef int foo_t;")
        assert ffi.list_types() == (['foo_t'], [], [])
        assert ffi.typeof('foo_t').kind == 'primitive'
        assert ffi.typeof('foo_t').cname == 'int'
        #
        ffi.cdef("typedef signed char a_t, c_t, g_t, b_t;")
        assert ffi.list_types() == (['a_t', 'b_t', 'c_t', 'foo_t', 'g_t'],
                                    [], [])

    def test_introspect_struct(self):
        ffi = FFI()
        ffi.cdef("struct foo_s { int a; };")
        assert ffi.list_types() == ([], ['foo_s'], [])
        assert ffi.typeof('struct foo_s').kind == 'struct'
        assert ffi.typeof('struct foo_s').cname == 'struct foo_s'

    def test_introspect_union(self):
        ffi = FFI()
        ffi.cdef("union foo_s { int a; };")
        assert ffi.list_types() == ([], [], ['foo_s'])
        assert ffi.typeof('union foo_s').kind == 'union'
        assert ffi.typeof('union foo_s').cname == 'union foo_s'

    def test_introspect_struct_and_typedef(self):
        ffi = FFI()
        ffi.cdef("typedef struct { int a; } foo_t;")
        assert ffi.list_types() == (['foo_t'], [], [])
        assert ffi.typeof('foo_t').kind == 'struct'
        assert ffi.typeof('foo_t').cname == 'foo_t'

    def test_introspect_included_type(self):
        ffi1 = FFI()
        ffi2 = FFI()
        ffi1.cdef("typedef signed char schar_t; struct sint_t { int x; };")
        ffi2.include(ffi1)
        assert ffi1.list_types() == ffi2.list_types() == (
            ['schar_t'], ['sint_t'], [])

    def test_introspect_order(self):
        ffi = FFI()
        ffi.cdef("union CFFIaaa { int a; }; typedef struct CFFIccc { int a; } CFFIb;")
        ffi.cdef("union CFFIg   { int a; }; typedef struct CFFIcc  { int a; } CFFIbbb;")
        ffi.cdef("union CFFIaa  { int a; }; typedef struct CFFIa   { int a; } CFFIbb;")
        assert ffi.list_types() == (['CFFIb', 'CFFIbb', 'CFFIbbb'],
                                    ['CFFIa', 'CFFIcc', 'CFFIccc'],
                                    ['CFFIaa', 'CFFIaaa', 'CFFIg'])

    def test_unpack(self):
        ffi = FFI()
        p = ffi.new("char[]", b"abc\x00def")
        assert ffi.unpack(p+1, 7) == b"bc\x00def\x00"
        p = ffi.new("int[]", [-123456789])
        assert ffi.unpack(p, 1) == [-123456789]

    def test_negative_array_size(self):
        ffi = FFI()
        pytest.raises(ValueError, ffi.cast, "int[-5]", 0)

    def test_cannot_instantiate_manually(self):
        ffi = FFI()
        ct = type(ffi.typeof("void *"))
        pytest.raises(TypeError, ct)
        pytest.raises(TypeError, ct, ffi.NULL)
        for cd in [type(ffi.cast("void *", 0)),
                   type(ffi.new("char[]", 3)),
                   type(ffi.gc(ffi.NULL, lambda x: None))]:
            pytest.raises(TypeError, cd)
            pytest.raises(TypeError, cd, ffi.NULL)
            pytest.raises(TypeError, cd, ffi.typeof("void *"))

    def test_explicitly_defined_char16_t(self):
        ffi = FFI()
        ffi.cdef("typedef uint16_t char16_t;")
        x = ffi.cast("char16_t", 1234)
        assert ffi.typeof(x) is ffi.typeof("uint16_t")

    def test_char16_t(self):
        ffi = FFI()
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
        ffi = FFI()
        x = ffi.new("char32_t[]", 5)
        assert len(x) == 5 and ffi.sizeof(x) == 20
        x[3] = u+'\U00013245'
        assert x[3] == u+'\U00013245'
        y = ffi.new("char32_t[]", u+'\u1234\u5678')
        assert len(y) == 3
        assert list(y) == [u+'\u1234', u+'\u5678', u+'\x00']
        py_uni = u+'\U00012345'
        z = ffi.new("char32_t[]", py_uni)
        assert len(z) == 2
        assert list(z) == [py_uni, u+'\x00']    # maybe a 2-unichars string
        assert ffi.string(z) == py_uni
        if len(py_uni) == 1:    # 4-bytes unicodes in Python
            s = ffi.new("char32_t[]", u+'\ud808\udf00')
            assert len(s) == 3
            assert list(s) == [u+'\ud808', u+'\udf00', u+'\x00']
