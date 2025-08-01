import sys, os, re
import shutil, subprocess, time
import pytest
from testing.udir import udir
import cffi


local_dir = os.path.dirname(os.path.abspath(__file__))
_link_error = '?'

def check_lib_python_found(tmpdir):
    global _link_error
    if _link_error == '?':
        ffi = cffi.FFI()
        kwds = {}
        ffi._apply_embedding_fix(kwds)
        ffi.set_source("_test_lib_python_found", "", **kwds)
        try:
            ffi.compile(tmpdir=tmpdir, verbose=True)
        except cffi.VerificationError as e:
            _link_error = e
        else:
            _link_error = None
    if _link_error:
        pytest.skip(str(_link_error))


def prefix_pythonpath():
    cffi_base = os.path.dirname(os.path.dirname(local_dir))
    pythonpath = org_env.get('PYTHONPATH', '').split(os.pathsep)
    if cffi_base not in pythonpath:
        pythonpath.insert(0, cffi_base)
    return os.pathsep.join(pythonpath)

def copy_away_env():
    global org_env
    try:
        org_env
    except NameError:
        org_env = os.environ.copy()

@pytest.mark.thread_unsafe(reason="Parallel tests would share a build directory")
class EmbeddingTests:
    _compiled_modules = {}

    def setup_method(self, meth):
        check_lib_python_found(str(udir.ensure('embedding', dir=1)))
        self._path = udir.join('embedding', meth.__name__)
        if sys.platform == "win32" or sys.platform == "darwin":
            self._compiled_modules.clear()   # workaround

    def get_path(self):
        return str(self._path.ensure(dir=1))

    def _run_base(self, args, **kwds):
        print('RUNNING:', args, kwds)
        return subprocess.Popen(args, **kwds)

    def _run(self, args):
        popen = self._run_base(args, cwd=self.get_path(),
                                 stdout=subprocess.PIPE,
                                 universal_newlines=True)
        output, _ = popen.communicate()
        err = popen.returncode
        if err:
            raise OSError(("popen failed with exit code %r: %r\n\n%s" % (
                err, args, output)).rstrip())
        print(output.rstrip())
        return output

    def prepare_module(self, name):
        self.patch_environment()
        if name not in self._compiled_modules:
            path = self.get_path()
            filename = '%s.py' % name
            # NOTE: if you have an .egg globally installed with an older
            # version of cffi, this will not work, because sys.path ends
            # up with the .egg before the PYTHONPATH entries.  I didn't
            # find a solution to that: we could hack sys.path inside the
            # script run here, but we can't hack it in the same way in
            # execute().
            pathname = os.path.join(path, filename)
            with open(pathname, 'w') as g:
                g.write('''
# https://bugs.python.org/issue23246
import sys
if sys.platform == 'win32':
    try:
        import setuptools
    except ImportError:
        pass
''')
                with open(os.path.join(local_dir, filename), 'r') as f:
                    g.write(f.read())

            output = self._run([sys.executable, pathname])
            match = re.compile(r"\bFILENAME: (.+)").search(output)
            assert match
            dynamic_lib_name = match.group(1)
            if sys.platform == 'win32':
                assert dynamic_lib_name.endswith('_cffi.dll')
            elif sys.platform == 'darwin':
                assert dynamic_lib_name.endswith('_cffi.dylib')
            else:
                assert dynamic_lib_name.endswith('_cffi.so')
            self._compiled_modules[name] = dynamic_lib_name
        return self._compiled_modules[name]

    def compile(self, name, modules, opt=False, threads=False, defines={}):
        path = self.get_path()
        filename = '%s.c' % name
        shutil.copy(os.path.join(local_dir, filename), path)
        shutil.copy(os.path.join(local_dir, 'thread-test.h'), path)
        import distutils.ccompiler
        curdir = os.getcwd()
        try:
            os.chdir(self.get_path())
            c = distutils.ccompiler.new_compiler()
            print('compiling %s with %r' % (name, modules))
            extra_preargs = []
            debug = True
            if sys.platform == 'win32':
                libfiles = []
                for m in modules:
                    m = os.path.basename(m)
                    assert m.endswith('.dll')
                    libfiles.append('Release\\%s.lib' % m[:-4])
                modules = libfiles
                extra_preargs.append('/MANIFEST')
                debug = False    # you need to install extra stuff
                                 # for this to work
            elif threads:
                extra_preargs.append('-pthread')
            objects = c.compile([filename], macros=sorted(defines.items()),
                                debug=debug)
            c.link_executable(objects + modules, name, extra_preargs=extra_preargs)
        finally:
            os.chdir(curdir)

    def patch_environment(self):
        copy_away_env()
        path = self.get_path()
        # for libpypy-c.dll or Python27.dll
        path = os.path.split(sys.executable)[0] + os.path.pathsep + path
        env_extra = {'PYTHONPATH': prefix_pythonpath()}
        if sys.platform == 'win32':
            envname = 'PATH'
        else:
            envname = 'LD_LIBRARY_PATH'
        libpath = org_env.get(envname)
        if libpath:
            libpath = path + os.path.pathsep + libpath
        else:
            libpath = path
        env_extra[envname] = libpath
        for key, value in sorted(env_extra.items()):
            if os.environ.get(key) != value:
                print('* setting env var %r to %r' % (key, value))
                os.environ[key] = value

    def execute(self, name):
        path = self.get_path()
        print('running %r in %r' % (name, path))
        executable_name = name
        if sys.platform == 'win32':
            executable_name = os.path.join(path, executable_name + '.exe')
        else:
            executable_name = os.path.join('.', executable_name)
        popen = self._run_base([executable_name], cwd=path,
                               stdout=subprocess.PIPE,
                               universal_newlines=True)
        result, _ = popen.communicate()
        err = popen.returncode
        if err:
            raise OSError("%r failed with exit code %r" % (
                os.path.join(path, executable_name), err))
        return result


class TestBasic(EmbeddingTests):
    def test_empty(self):
        empty_cffi = self.prepare_module('empty')
        self.compile('empty-test', [empty_cffi])
        output = self.execute('empty-test')
        assert output == 'OK\n'

    def test_basic(self):
        add1_cffi = self.prepare_module('add1')
        self.compile('add1-test', [add1_cffi])
        output = self.execute('add1-test')
        assert output == ("preparing...\n"
                          "adding 40 and 2\n"
                          "adding 100 and -5\n"
                          "got: 42 95\n")

    def test_two_modules(self):
        add1_cffi = self.prepare_module('add1')
        add2_cffi = self.prepare_module('add2')
        self.compile('add2-test', [add1_cffi, add2_cffi])
        output = self.execute('add2-test')
        assert output == ("preparing...\n"
                          "adding 40 and 2\n"
                          "prepADD2\n"
                          "adding 100 and -5 and -20\n"
                          "got: 42 75\n")

    def test_init_time_error(self):
        initerror_cffi = self.prepare_module('initerror')
        self.compile('add1-test', [initerror_cffi])
        output = self.execute('add1-test')
        assert output == "got: 0 0\n"    # plus lots of info to stderr

    def test_embedding_with_unicode(self):
        withunicode_cffi = self.prepare_module('withunicode')
        self.compile('add1-test', [withunicode_cffi])
        output = self.execute('add1-test')
        assert output == "255\n4660\n65244\ngot: 0 0\n"
