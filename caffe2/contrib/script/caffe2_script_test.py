from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from hypothesis import given

from caffe2.python import core, workspace
import caffe2.python.hypothesis_test_util as hu
import hypothesis.strategies as st

import numpy as np


class TestCaffe2Script(hu.HypothesisTestCase):
    test_program = """
          def foo(a,b,X,W) -> (c):
              t = a + b*b
              c = FC(X,W,t)
          def testIf(c0,c1,t,f) -> (r):
              if c0 < c1:
                  r = t
              else:
                  r = f
              r = Add(r,3f,broadcast=1)
          def testWhile(r) -> (r):
              m = 0
              while m < 4:
                  # Plus operator automatically broadcasts, and we cannot
                  # do in-place B and C arguments when we broadcast, so use
                  # an explicit Add op.
                  r = Add(r, r)
                  m = m + 1
      """

    @given(firstdim=st.integers(min_value=1, max_value=4096),
           seconddim=st.integers(min_value=1, max_value=4096),
           seed=st.integers(min_value=0, max_value=65536),
           **hu.gcs)
    def test_foo(self, firstdim, seconddim, seed, gc, dc):
        np.random.seed(int(seed))
        inputs = {}
        a = inputs['a'] = np.random.rand(seconddim).astype(np.float32)
        b = inputs['b'] = np.random.rand(seconddim).astype(np.float32)
        X = inputs['X'] = np.random.rand(firstdim, firstdim).astype(np.float32)
        W = inputs['W'] = np.random.rand(seconddim, firstdim).astype(np.float32)

        for name, inp in inputs.items():
            workspace.FeedBlob(name, inp)

        CU = core.C.CompilationUnit()
        CU.define(self.test_program)
        CU.create_net('foo').run()

        ref_t = a + b * b
        ref_c = np.matmul(X, W.transpose()) + ref_t
        actual_c = workspace.FetchBlob('c')

        np.testing.assert_allclose(actual_c, ref_c, rtol=1e-05)

    def test_trinary(self):
        CU = core.C.CompilationUnit()
        CU.define("""
            def foo(c) -> (d):
                d = 1 + (2 if c else 4)
        """)
        workspace.FeedBlob('c', np.ones((1), dtype=bool))
        net = CU.create_net('foo')
        net.run()
        assert(3 == workspace.FetchBlob('d'))
        workspace.FeedBlob('c', np.zeros((1), dtype=bool))
        net.run()
        assert(5 == workspace.FetchBlob('d'))

    def test_bool_literal(self):
        CU = core.C.CompilationUnit()
        CU.define("""
            def foo() -> (a,b):
                a = True
                b = False
        """)
        net = CU.create_net('foo')
        net.run()
        assert(workspace.FetchBlob('a'))
        assert(not workspace.FetchBlob('b'))

    def test_bool_operators(self):
        CU = core.C.CompilationUnit()
        CU.define("""
            def foo() -> (a, b, c, d, e):
                a = True and False
                b = True or False
                c = not b
                d = not False or True
                e = not (1 if a else 0) == (1 if b else 0)
        """)
        net = CU.create_net('foo')
        net.run()
        assert(not workspace.FetchBlob('a'))
        assert(workspace.FetchBlob('b'))
        assert(not workspace.FetchBlob('c'))
        assert(workspace.FetchBlob('d'))
        assert(workspace.FetchBlob('e'))

    def test_print(self):
        CU = core.C.CompilationUnit()
        CU.define("""
            def foo() -> ():
                a = 1
                Print(a)
                Print(a+1)
                _ = 4
                Print(_) # verify in print this isn't _ but some temorary
                Print(1)
                Print(1.f)
                Print(3.0)
        """)
        net = CU.create_net('foo')
        net.run()

    def test_method(self):
        CU = core.C.CompilationUnit()
        CU.define("""
            def foo() -> (a):
                a = (3+1).Add(4).Add(1)
        """)
        net = CU.create_net('foo')
        net.run()
        assert(9 == workspace.FetchBlob('a'))

    def test_plus_eq(self):
        CU = core.C.CompilationUnit()
        CU.define("""
            def foo() -> (a):
                a = 4
                a += 1
        """)
        net = CU.create_net('foo')
        net.run()
        assert(5 == workspace.FetchBlob('a'))

    def test_cast(self):
        CU = core.C.CompilationUnit()
        CU.define("""
            def foo() -> (a):
                a = int(4.5f)
        """)
        net = CU.create_net('foo')
        net.run()
        assert(4 == workspace.FetchBlob('a'))

    @given(seed=st.integers(min_value=0, max_value=65536), **hu.gcs)
    def test_if(self, seed, gc, dc):
        np.random.seed(int(seed))
        inputs = {}
        c0 = inputs['c0'] = np.random.rand(1).astype(np.float32)
        c1 = inputs['c1'] = np.random.rand(1).astype(np.float32)
        t = inputs['t'] = np.random.rand(3, 3).astype(np.float32)
        f = inputs['f'] = np.random.rand(3, 3).astype(np.float32)

        for name, inp in inputs.items():
            workspace.FeedBlob(name, inp)

        CU = core.C.CompilationUnit()
        CU.define(self.test_program)
        CU.create_net('testIf').run()

        if c0 < c1:
            ref_r = t + 3
        else:
            ref_r = f + 3
        actual_r = workspace.FetchBlob('r')

        np.testing.assert_allclose(actual_r, ref_r)

    @given(seed=st.integers(min_value=0, max_value=65536), **hu.gcs)
    def test_while(self, seed, gc, dc):
        np.random.seed(int(seed))
        inputs = {}
        r = inputs['r'] = np.ones([3, 3]).astype(np.float32)

        for name, inp in inputs.items():
            workspace.FeedBlob(name, inp)

        CU = core.C.CompilationUnit()
        CU.define(self.test_program)
        CU.create_net('testWhile').run()

        m = 0
        while m < 4:
            r = r + r
            m = m + 1

        actual_r = workspace.FetchBlob('r')

        np.testing.assert_allclose(actual_r, r)
