from unittest.mock import MagicMock

import pytest

from unstructured_platform_plugins.invocation_settings import (
    SettingsScopedCache,
    settings_cache_key,
)


class TestSettingsCacheKey:
    def test_key_is_insensitive_to_key_order(self):
        assert settings_cache_key({"a": 1, "b": 2}) == settings_cache_key({"b": 2, "a": 1})

    def test_key_is_sensitive_to_values(self):
        assert settings_cache_key({"a": 1}) != settings_cache_key({"a": 2})

    def test_secret_values_do_not_appear_in_the_key(self):
        secret = "sk-super-secret-credential"
        key = settings_cache_key({"api_key": secret})
        assert secret not in key


class TestSettingsScopedCache:
    def test_second_lookup_with_same_settings_does_not_rebuild(self):
        cache = SettingsScopedCache()
        build = MagicMock(return_value="handler")

        first = cache.get_or_build({"model": "a"}, build)
        second = cache.get_or_build({"model": "a"}, build)

        assert first == second == "handler"
        build.assert_called_once()

    def test_change_in_resolved_field_builds_a_distinct_value(self):
        cache = SettingsScopedCache()

        first = cache.get_or_build({"model": "a"}, lambda: object())
        second = cache.get_or_build({"model": "b"}, lambda: object())

        assert first is not second

    def test_entry_expires_after_ttl(self):
        now = [0.0]
        cache = SettingsScopedCache(ttl_seconds=10, clock=lambda: now[0])
        build = MagicMock(return_value="handler")

        cache.get_or_build({"model": "a"}, build)
        now[0] = 11.0
        cache.get_or_build({"model": "a"}, build)

        assert build.call_count == 2

    def test_entry_survives_within_ttl(self):
        now = [0.0]
        cache = SettingsScopedCache(ttl_seconds=10, clock=lambda: now[0])
        build = MagicMock(return_value="handler")

        cache.get_or_build({"model": "a"}, build)
        now[0] = 9.0
        cache.get_or_build({"model": "a"}, build)

        build.assert_called_once()

    def test_size_bound_evicts_least_recently_used(self):
        cache = SettingsScopedCache(maxsize=2)
        builds = {name: MagicMock(return_value=name) for name in ("a", "b", "c")}

        cache.get_or_build({"model": "a"}, builds["a"])
        cache.get_or_build({"model": "b"}, builds["b"])
        # Refresh "a" so "b" is the eviction candidate when "c" lands.
        cache.get_or_build({"model": "a"}, builds["a"])
        cache.get_or_build({"model": "c"}, builds["c"])

        cache.get_or_build({"model": "a"}, builds["a"])
        cache.get_or_build({"model": "b"}, builds["b"])

        builds["a"].assert_called_once()
        assert builds["b"].call_count == 2

    def test_clear_forces_rebuild(self):
        cache = SettingsScopedCache()
        build = MagicMock(return_value="handler")

        cache.get_or_build({"model": "a"}, build)
        cache.clear()
        cache.get_or_build({"model": "a"}, build)

        assert build.call_count == 2

    @pytest.mark.parametrize("kwargs", [{"ttl_seconds": 0}, {"ttl_seconds": -1}, {"maxsize": 0}])
    def test_degenerate_bounds_are_rejected(self, kwargs):
        with pytest.raises(ValueError):
            SettingsScopedCache(**kwargs)


class TestHandlerFor:
    def test_absent_settings_return_the_boot_handler(self):
        cache = SettingsScopedCache()
        build = MagicMock()

        handler = cache.handler_for(None, boot=lambda: "boot-handler", build=build)

        assert handler == "boot-handler"
        build.assert_not_called()

    def test_absent_settings_without_a_boot_handler_fail(self):
        cache = SettingsScopedCache()

        with pytest.raises(ValueError):
            cache.handler_for(None, boot=lambda: None, build=MagicMock())

    def test_resolved_settings_build_and_cache_per_distinct_mapping(self):
        cache = SettingsScopedCache()
        boot = MagicMock()
        build = MagicMock(return_value="handler")

        first = cache.handler_for({"model": "a"}, boot=boot, build=build)
        second = cache.handler_for({"model": "a"}, boot=boot, build=build)

        assert first == second == "handler"
        build.assert_called_once()
        boot.assert_not_called()
