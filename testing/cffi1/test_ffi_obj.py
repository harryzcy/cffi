import sys
import pytest
import _cffi_backend as _cffi1_backend


def test_ffi_new():
    ffi = _cffi1_backend.FFI()
    p = ffi.new("int *")
    p[0] = -42
    assert p[0] == -42
    assert type(ffi) is ffi.__class__ is _cffi1_backend.FFI

def test_ffi_subclass():
    class FOO(_cffi1_backend.FFI):
        def __init__(self, x):
            self.x = x
    foo = FOO(42)
    assert foo.x == 42
    p = foo.new("int *")
    assert p[0] == 0
    assert type(foo) is foo.__class__ is FOO

def test_ffi_no_argument():
    pytest.raises(TypeError, _cffi1_backend.FFI, 42)

def test_ffi_cache_type():
    ffi = _cffi1_backend.FFI()
    t1 = ffi.typeof("int **")
    t2 = ffi.typeof("int *")
    assert t2.item is t1.item.item
    assert t2 is t1.item
    assert ffi.typeof("int[][10]") is ffi.typeof("int[][10]")
    assert ffi.typeof("int(*)()") is ffi.typeof("int(*)()")

@pytest.mark.thread_unsafe(reason="May not pass if other threads unexpectedly trigger the gc")
def test_ffi_type_not_immortal():
    import weakref, gc
    ffi = _cffi1_backend.FFI()
    # this test can fail on free-threaded builds lazier GC if the type was used by another test
    t1 = ffi.typeof("unsigned short int **")
    t2 = ffi.typeof("unsigned short int *")
    w1 = weakref.ref(t1)
    w2 = weakref.ref(t2)
    del t1, ffi
    gc.collect()
    assert w1() is None
    assert w2() is t2
    ffi = _cffi1_backend.FFI()
    assert ffi.typeof(ffi.new("unsigned short int **")[0]) is t2
    #
    ffi = _cffi1_backend.FFI()
    t1 = ffi.typeof("int ***")
    t2 = ffi.typeof("int **")
    w1 = weakref.ref(t1)
    w2 = weakref.ref(t2)
    del t2, ffi
    gc.collect()
    assert w1() is t1
    assert w2() is not None   # kept alive by t1
    ffi = _cffi1_backend.FFI()
    assert ffi.typeof("int * *") is t1.item

def test_ffi_cache_type_globally():
    ffi1 = _cffi1_backend.FFI()
    ffi2 = _cffi1_backend.FFI()
    t1 = ffi1.typeof("int *")
    t2 = ffi2.typeof("int *")
    assert t1 is t2

def test_ffi_invalid():
    ffi = _cffi1_backend.FFI()
    # array of 10 times an "int[]" is invalid
    pytest.raises(ValueError, ffi.typeof, "int[10][]")

def test_ffi_docstrings():
    # check that all methods of the FFI class have a docstring.
    check_type = type(_cffi1_backend.FFI.new)
    for methname in dir(_cffi1_backend.FFI):
        if not methname.startswith('_'):
            method = getattr(_cffi1_backend.FFI, methname)
            if isinstance(method, check_type):
                assert method.__doc__, "method FFI.%s() has no docstring" % (
                    methname,)

def test_ffi_NULL():
    NULL = _cffi1_backend.FFI.NULL
    assert _cffi1_backend.FFI().typeof(NULL).cname == "void *"

def test_ffi_no_attr():
    ffi = _cffi1_backend.FFI()
    with pytest.raises(AttributeError):
        ffi.no_such_name
    with pytest.raises(AttributeError):
        ffi.no_such_name = 42
    with pytest.raises(AttributeError):
        del ffi.no_such_name

def test_ffi_string():
    ffi = _cffi1_backend.FFI()
    p = ffi.new("char[]", init=b"foobar\x00baz")
    assert ffi.string(p) == b"foobar"
    assert ffi.string(cdata=p, maxlen=3) == b"foo"

def test_ffi_errno():
    # xxx not really checking errno, just checking that we can read/write it
    ffi = _cffi1_backend.FFI()
    ffi.errno = 42
    assert ffi.errno == 42

def test_ffi_alignof():
    ffi = _cffi1_backend.FFI()
    assert ffi.alignof("int") == 4
    assert ffi.alignof("int[]") == 4
    assert ffi.alignof("int[41]") == 4
    assert ffi.alignof("short[41]") == 2
    assert ffi.alignof(ffi.new("int[41]")) == 4
    assert ffi.alignof(ffi.new("int[]", 41)) == 4

def test_ffi_sizeof():
    ffi = _cffi1_backend.FFI()
    assert ffi.sizeof("int") == 4
    pytest.raises(ffi.error, ffi.sizeof, "int[]")
    assert ffi.sizeof("int[41]") == 41 * 4
    assert ffi.sizeof(ffi.new("int[41]")) == 41 * 4
    assert ffi.sizeof(ffi.new("int[]", 41)) == 41 * 4

def test_ffi_callback():
    ffi = _cffi1_backend.FFI()
    assert ffi.callback("int(int)", lambda x: x + 42)(10) == 52
    assert ffi.callback("int(*)(int)", lambda x: x + 42)(10) == 52
    assert ffi.callback("int(int)", lambda x: x + "", -66)(10) == -66
    assert ffi.callback("int(int)", lambda x: x + "", error=-66)(10) == -66

def test_ffi_callback_decorator():
    ffi = _cffi1_backend.FFI()
    assert ffi.callback(ffi.typeof("int(*)(int)"))(lambda x: x + 42)(10) == 52
    deco = ffi.callback("int(int)", error=-66)
    assert deco(lambda x: x + "")(10) == -66
    assert deco(lambda x: x + 42)(10) == 52

def test_ffi_callback_onerror():
    ffi = _cffi1_backend.FFI()
    seen = []
    def oops(*args):
        seen.append(args)

    @ffi.callback("int(int)", onerror=oops)
    def fn1(x):
        return x + ""
    assert fn1(10) == 0

    @ffi.callback("int(int)", onerror=oops, error=-66)
    def fn2(x):
        return x + ""
    assert fn2(10) == -66

    assert len(seen) == 2
    exc, val, tb = seen[0]
    assert exc is TypeError
    assert isinstance(val, TypeError)
    assert tb.tb_frame.f_code.co_name == "fn1"
    exc, val, tb = seen[1]
    assert exc is TypeError
    assert isinstance(val, TypeError)
    assert tb.tb_frame.f_code.co_name == "fn2"
    #
    pytest.raises(TypeError, ffi.callback, "int(int)",
                   lambda x: x, onerror=42)   # <- not callable

def test_ffi_getctype():
    ffi = _cffi1_backend.FFI()
    assert ffi.getctype("int") == "int"
    assert ffi.getctype("int", 'x') == "int x"
    assert ffi.getctype("int*") == "int *"
    assert ffi.getctype("int*", '') == "int *"
    assert ffi.getctype("int*", 'x') == "int * x"
    assert ffi.getctype("int", '*') == "int *"
    assert ffi.getctype("int", replace_with=' * x ') == "int * x"
    assert ffi.getctype(ffi.typeof("int*"), '*') == "int * *"
    assert ffi.getctype("int", '[5]') == "int[5]"
    assert ffi.getctype("int[5]", '[6]') == "int[6][5]"
    assert ffi.getctype("int[5]", '(*)') == "int(*)[5]"
    # special-case for convenience: automatically put '()' around '*'
    assert ffi.getctype("int[5]", '*') == "int(*)[5]"
    assert ffi.getctype("int[5]", '*foo') == "int(*foo)[5]"
    assert ffi.getctype("int[5]", ' ** foo ') == "int(** foo)[5]"

def test_addressof():
    ffi = _cffi1_backend.FFI()
    a = ffi.new("int[10]")
    b = ffi.addressof(a, 5)
    b[2] = -123
    assert a[7] == -123

def test_handle():
    ffi = _cffi1_backend.FFI()
    x = [2, 4, 6]
    xp = ffi.new_handle(x)
    assert ffi.typeof(xp) == ffi.typeof("void *")
    assert ffi.from_handle(xp) is x
    yp = ffi.new_handle([6, 4, 2])
    assert ffi.from_handle(yp) == [6, 4, 2]

def test_handle_unique():
    ffi = _cffi1_backend.FFI()
    assert ffi.new_handle(None) is not ffi.new_handle(None)
    assert ffi.new_handle(None) != ffi.new_handle(None)

def test_ffi_cast():
    ffi = _cffi1_backend.FFI()
    assert ffi.cast("int(*)(int)", 0) == ffi.NULL
    ffi.callback("int(int)")      # side-effect of registering this string
    pytest.raises(ffi.error, ffi.cast, "int(int)", 0)

def test_ffi_invalid_type():
    ffi = _cffi1_backend.FFI()
    e = pytest.raises(ffi.error, ffi.cast, "", 0)
    assert str(e.value) == ("identifier expected\n"
                            "\n"
                            "^")
    e = pytest.raises(ffi.error, ffi.cast, "struct struct", 0)
    assert str(e.value) == ("struct or union name expected\n"
                            "struct struct\n"
                            "       ^")
    e = pytest.raises(ffi.error, ffi.cast, "struct never_heard_of_s", 0)
    assert str(e.value) == ("undefined struct/union name\n"
                            "struct never_heard_of_s\n"
                            "       ^")
    e = pytest.raises(ffi.error, ffi.cast, "\t\n\x01\x1f~\x7f\x80\xff", 0)
    marks = "?" if sys.version_info < (3,) else "??"
    assert str(e.value) == ("identifier expected\n"
                            "  ??~?%s%s\n"
                            "  ^" % (marks, marks))
    e = pytest.raises(ffi.error, ffi.cast, "X" * 600, 0)
    assert str(e.value) == ("undefined type name")

def test_ffi_buffer():
    ffi = _cffi1_backend.FFI()
    a = ffi.new("signed char[]", [5, 6, 7])
    assert ffi.buffer(a)[:] == b'\x05\x06\x07'
    assert ffi.buffer(cdata=a, size=2)[:] == b'\x05\x06'
    assert type(ffi.buffer(a)) is ffi.buffer

def test_ffi_from_buffer():
    import array
    ffi = _cffi1_backend.FFI()
    a = array.array('H', [10000, 20000, 30000, 40000])
    c = ffi.from_buffer(a)
    assert ffi.typeof(c) is ffi.typeof("char[]")
    assert len(c) == 8
    ffi.cast("unsigned short *", c)[1] += 500
    assert list(a) == [10000, 20500, 30000, 40000]
    pytest.raises(TypeError, ffi.from_buffer, a, True)
    assert c == ffi.from_buffer("char[]", a, True)
    assert c == ffi.from_buffer(a, require_writable=True)
    #
    c = ffi.from_buffer("unsigned short[]", a)
    assert len(c) == 4
    assert c[1] == 20500
    #
    c = ffi.from_buffer("unsigned short[2][2]", a)
    assert len(c) == 2
    assert len(c[0]) == 2
    assert c[0][1] == 20500
    #
    p = ffi.from_buffer(b"abcd")
    assert p[2] == b"c"
    #
    assert p == ffi.from_buffer(b"abcd", require_writable=False)
    pytest.raises((TypeError, BufferError), ffi.from_buffer,
                                             "char[]", b"abcd", True)
    pytest.raises((TypeError, BufferError), ffi.from_buffer, b"abcd",
                                             require_writable=True)

def test_memmove():
    ffi = _cffi1_backend.FFI()
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

def test_memmove_buffer():
    import array
    ffi = _cffi1_backend.FFI()
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

def test_memmove_readonly_readwrite():
    ffi = _cffi1_backend.FFI()
    p = ffi.new("signed char[]", 5)
    ffi.memmove(p, b"abcde", 3)
    assert list(p) == [ord("a"), ord("b"), ord("c"), 0, 0]
    ffi.memmove(p, bytearray(b"ABCDE"), 2)
    assert list(p) == [ord("A"), ord("B"), ord("c"), 0, 0]
    pytest.raises((TypeError, BufferError), ffi.memmove, b"abcde", p, 3)
    ba = bytearray(b"xxxxx")
    ffi.memmove(dest=ba, src=p, n=3)
    assert ba == bytearray(b"ABcxx")

def test_ffi_types():
    CData = _cffi1_backend.FFI.CData
    CType = _cffi1_backend.FFI.CType
    ffi = _cffi1_backend.FFI()
    assert isinstance(ffi.cast("int", 42), CData)
    assert isinstance(ffi.typeof("int"), CType)

def test_ffi_getwinerror():
    if sys.platform != "win32":
        pytest.skip("for windows")
    ffi = _cffi1_backend.FFI()
    n = (1 << 29) + 42
    code, message = ffi.getwinerror(code=n)
    assert code == n

def test_ffi_new_allocator_1():
    ffi = _cffi1_backend.FFI()
    alloc1 = ffi.new_allocator()
    alloc2 = ffi.new_allocator(should_clear_after_alloc=False)
    for retry in range(400):
        p1 = alloc1("int[10]")
        p2 = alloc2("int[]", 10 + retry * 13)
        combination = 0
        for i in range(10):
            assert p1[i] == 0
            combination |= p2[i]
            p1[i] = -42
            p2[i] = -43
        if combination != 0:
            break
    else:
        raise AssertionError("cannot seem to get an int[10] not "
                             "completely cleared")

def test_ffi_new_allocator_2():
    ffi = _cffi1_backend.FFI()
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
    assert (seen == [40, 40, raw1, raw2] or
            seen == [40, 40, raw2, raw1])
    assert repr(seen[2]) == "<cdata 'char[]' owning 41 bytes>"
    assert repr(seen[3]) == "<cdata 'char[]' owning 41 bytes>"

def test_ffi_new_allocator_3():
    ffi = _cffi1_backend.FFI()
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

def test_ffi_new_allocator_4():
    ffi = _cffi1_backend.FFI()
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

def test_bool_issue228():
    ffi = _cffi1_backend.FFI()
    fntype = ffi.typeof("int(*callback)(bool is_valid)")
    assert repr(fntype.args[0]) == "<ctype '_Bool'>"

def test_FILE_issue228():
    fntype1 = _cffi1_backend.FFI().typeof("FILE *")
    fntype2 = _cffi1_backend.FFI().typeof("FILE *")
    assert repr(fntype1) == "<ctype 'FILE *'>"
    assert fntype1 is fntype2

def test_cast_from_int_type_to_bool():
    ffi = _cffi1_backend.FFI()
    for basetype in ['char', 'short', 'int', 'long', 'long long']:
        for sign in ['signed', 'unsigned']:
            type = '%s %s' % (sign, basetype)
            assert int(ffi.cast("_Bool", ffi.cast(type, 42))) == 1
            assert int(ffi.cast("bool", ffi.cast(type, 42))) == 1
            assert int(ffi.cast("_Bool", ffi.cast(type, 0))) == 0

def test_init_once():
    def do_init():
        seen.append(1)
        return 42
    ffi = _cffi1_backend.FFI()
    seen = []
    for i in range(3):
        res = ffi.init_once(do_init, "tag1")
        assert res == 42
        assert seen == [1]
    for i in range(3):
        res = ffi.init_once(do_init, "tag2")
        assert res == 42
        assert seen == [1, 1]

def test_init_once_multithread():
    if sys.version_info < (3,):
        import thread
    else:
        import _thread as thread
    import time
    #
    def do_init():
        print('init!')
        seen.append('init!')
        time.sleep(1)
        seen.append('init done')
        print('init done')
        return 7
    ffi = _cffi1_backend.FFI()
    seen = []
    for i in range(6):
        def f():
            res = ffi.init_once(do_init, "tag")
            seen.append(res)
        thread.start_new_thread(f, ())
    time.sleep(1.5)
    assert seen == ['init!', 'init done'] + 6 * [7]

def test_init_once_failure():
    def do_init():
        seen.append(1)
        raise ValueError
    ffi = _cffi1_backend.FFI()
    seen = []
    for i in range(5):
        pytest.raises(ValueError, ffi.init_once, do_init, "tag")
        assert seen == [1] * (i + 1)

def test_init_once_multithread_failure():
    if sys.version_info < (3,):
        import thread
    else:
        import _thread as thread
    import time
    def do_init():
        seen.append('init!')
        time.sleep(1)
        seen.append('oops')
        raise ValueError
    ffi = _cffi1_backend.FFI()
    seen = []
    for i in range(3):
        def f():
            pytest.raises(ValueError, ffi.init_once, do_init, "tag")
        thread.start_new_thread(f, ())
    i = 0
    while len(seen) < 6:
        i += 1
        assert i < 20
        time.sleep(0.51)
    assert seen == ['init!', 'oops'] * 3

def test_unpack():
    ffi = _cffi1_backend.FFI()
    p = ffi.new("char[]", b"abc\x00def")
    assert ffi.unpack(p+1, 7) == b"bc\x00def\x00"
    p = ffi.new("int[]", [-123456789])
    assert ffi.unpack(p, 1) == [-123456789]

def test_negative_array_size():
    ffi = _cffi1_backend.FFI()
    pytest.raises(ffi.error, ffi.cast, "int[-5]", 0)
