"""Test runner that isolates cache state (DRF throttle counters) per test.

DRF's cache-based throttles persist counters in the default cache. Without
isolation, one test's requests can trip another test's rate limits. This
runner flushes the cache before and after every test so each starts clean,
while the application code itself is unchanged.
"""

import types
import unittest
from functools import wraps

from django.core.cache import cache
from django.test.runner import DiscoverRunner


def _flushing(method, flush_after=False):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        cache.clear()
        result = method(self, *args, **kwargs)
        if flush_after:
            cache.clear()
        return result

    return wrapper


class CacheIsolatingRunner(DiscoverRunner):
    """DiscoverRunner that clears the cache around every test.

    Used only through ``manage.py test`` (TEST_RUNNER setting); production
    behavior is untouched.
    """

    def run_suite(self, suite, **kwargs):
        for test in _iter_tests(suite):
            if isinstance(getattr(test, "setUp", None), types.MethodType):
                # Rebind as instance methods — assigning a plain function
                # would drop ``self``.
                test.setUp = types.MethodType(_flushing(test.setUp.__func__), test)
                test.tearDown = types.MethodType(
                    _flushing(test.tearDown.__func__, flush_after=True), test
                )
        return super().run_suite(suite, **kwargs)


def _iter_tests(suite):
    """Yield every unittest.TestCase in a (possibly nested) suite."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_tests(item)
        else:
            yield item
