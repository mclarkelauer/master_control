from unittest.mock import patch

from master_control.engine.rlimits import make_preexec_fn


class TestMakePreexecFn:
    def test_returns_none_when_no_limits(self) -> None:
        assert make_preexec_fn() is None
        assert make_preexec_fn(memory_limit_mb=None, cpu_nice=None) is None

    def test_sets_memory_limit(self) -> None:
        fn = make_preexec_fn(memory_limit_mb=128)
        assert fn is not None

        with patch("resource.setrlimit") as mock_setrlimit:
            fn()
            expected_bytes = 128 * 1024 * 1024
            mock_setrlimit.assert_called_once()
            args = mock_setrlimit.call_args
            assert args[0][1] == (expected_bytes, expected_bytes)

    def test_sets_nice(self) -> None:
        fn = make_preexec_fn(cpu_nice=10)
        assert fn is not None

        with patch("os.nice") as mock_nice:
            fn()
            mock_nice.assert_called_once_with(10)

    def test_sets_both(self) -> None:
        fn = make_preexec_fn(memory_limit_mb=64, cpu_nice=5)
        assert fn is not None

        with patch("resource.setrlimit") as mock_setrlimit, patch("os.nice") as mock_nice:
            fn()
            expected_bytes = 64 * 1024 * 1024
            mock_setrlimit.assert_called_once()
            assert mock_setrlimit.call_args[0][1] == (expected_bytes, expected_bytes)
            mock_nice.assert_called_once_with(5)

    def test_returns_callable(self) -> None:
        fn = make_preexec_fn(memory_limit_mb=256)
        assert callable(fn)
