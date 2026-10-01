"""The Plex library script only adds what is missing and is gated."""

from plex_libraries import apply_allowed, diff, load_config


def test_config_is_complete():
    config = load_config()
    assert config["server"] == "workstation"
    assert {lib["name"] for lib in config["libraries"]} == {"Movies"}
    assert config["settings"]["PublishServerOnPlexOnlineKey"] is False


def test_missing_library_is_added():
    config = load_config()
    actions = diff(config, sections=[], settings={})
    assert [(a.kind, a.name) for a in actions] == [("add-library", "Movies")]


def test_existing_matching_library_needs_nothing():
    config = load_config()
    movies = config["libraries"][0]
    sections = [{"name": "Movies", "type": "movie", "locations": movies["locations"]}]
    assert diff(config, sections, {"PublishServerOnPlexOnlineKey": False}) == []


def test_drift_is_reported_never_fixed():
    config = load_config()
    sections = [{"name": "Movies", "type": "show", "locations": []}]
    kinds = {a.kind for a in diff(config, sections, {"PublishServerOnPlexOnlineKey": True})}
    assert kinds == {"library-drift", "setting-drift"}


def test_apply_needs_the_flag_and_the_exact_confirmation():
    config = load_config()
    assert not apply_allowed(config, env={})
    assert not apply_allowed(config, env={"PLEX_ALLOW_APPLY": "true", "PLEX_CONFIRMATION": "yes"})
    assert apply_allowed(
        config, env={"PLEX_ALLOW_APPLY": "true", "PLEX_CONFIRMATION": "PLEX LIBRARIES workstation"}
    )
