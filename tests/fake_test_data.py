from __future__ import annotations

test_method_one = \
    """
    import time

    def func(x):
        return x + 1

    def test_slow():
        time.sleep(1.5)
        assert func(4) == 5

    # FAIL
    def test_fast_fail():
        time.sleep(0.5)
        assert func(3) == 5

    def test_medium():
        time.sleep(1)
        assert func(4) == 5
    """


test_class_one = \
    """
    import time

    def func(x):
        return x + 1

    class TestClassSample:
        def test_fast(self):
            time.sleep(0.7)
            assert func(4) == 5

        # FAIL
        def test_slow_fail(self):
            time.sleep(1.7)
            assert func(3) == 5

        def test_medium(self):
            time.sleep(1.2)
            assert func(4) == 5
    """


test_put_one = \
    """
    import pytest

    @pytest.mark.parametrize("param", {"a", "b", "c", "d"})
    def test_put_unordered(param):
        pass

    @pytest.mark.parametrize("param", ["d", "e", 1, 3, "a", "b", " "])
    def test_put_ordered(param):
        pass

    """


test_a_method = \
    """
    import time

    def func(x):
        return x + 1

    def test_a_slow():
        time.sleep(1.5)
        assert func(4) == 5

    # FAIL
    def test_b_fast_fail():
        time.sleep(0.5)
        assert func(3) == 5

    def test_c_medium():
        time.sleep(1)
        assert func(4) == 5
    """


test_b_class = \
    """
    import time

    def func(x):
        return x + 1

    class TestClassA:
        def test_a_fast(self):
            time.sleep(0.7)
            assert func(4) == 5

        # FAIL
        def test_b_slow_fail(self):
            time.sleep(1.7)
            assert func(3) == 5

        def test_c_medium(self):
            time.sleep(1.2)
            assert func(4) == 5
    """


test_c_put = \
    """
    import pytest
    import time

    @pytest.mark.parametrize("param", {0.1, 0.2, 0.3, 0.4})
    def test_a_put_unordered(param):
        time.sleep(param)
        pass

    @pytest.mark.parametrize("param", [0.45, 0.25, 0.55, 0.35, 0.15])
    def test_b_put_ordered(param):
        time.sleep(param)
        pass

    """


test_c_put_ordered = \
    """
    import pytest
    import time

    @pytest.mark.parametrize("param", [0.45, 0.25, 0.55, 0.35, 0.15])
    def test_b_put_ordered(param):
        time.sleep(param)
        pass

    """


test_a_method_two = \
    """
    import time

    def func(x):
        return x + 1

    def test_a_slow():
        time.sleep(0.05)
        assert func(4) == 5

    # FAIL
    def test_b_fast_fail():
        time.sleep(0.01)
        assert func(3) == 5

    def test_c_medium():
        time.sleep(0.02)
        assert func(4) == 5
    """


test_order = \
    """
    import pytest
    import time
    @pytest.mark.order(2)
    def test_foo():
        time.sleep(4.5)
        assert True

    @pytest.mark.order(1)
    def test_bar():
        time.sleep(5)
        assert True
    """


test_dependency = \
    """
    import pytest
    import time

    @pytest.mark.dependency()
    @pytest.mark.xfail(reason="deliberate fail")
    def test_a():
        time.sleep(4)
        assert False

    @pytest.mark.dependency()
    def test_b():
        time.sleep(3.5)
        pass

    @pytest.mark.dependency(depends=["test_a"])
    def test_c():
        time.sleep(3)
        pass

    @pytest.mark.dependency(depends=["test_b"])
    def test_d():
        time.sleep(2.5)
        pass

    @pytest.mark.dependency(depends=["test_b", "test_c"])
    def test_e():
        time.sleep(2)
        pass
    """


replay_order_one = \
    """
    test_class_one.py::TestClassSample::test_fast
    test_class_one.py::TestClassSample::test_slow_fail
    test_method_one.py::test_medium
    test_method_one.py::test_fast_fail
    test_class_one.py::TestClassSample::test_medium
    test_method_one.py::test_slow
    """
