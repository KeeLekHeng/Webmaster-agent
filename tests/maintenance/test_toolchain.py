import pytest
from guardian.maintenance.policy import BROWSER_PACKAGES, deferred_updates, toolchain_versions


def test_browser_version_comes_from_reviewed_image(tmp_path):
    (tmp_path/'Dockerfile').write_text('# comment\nFROM mcr.microsoft.com/playwright:v1.62.1-noble\nRUN echo synthetic\n')
    assert toolchain_versions(tmp_path)=={name:'1.62.1' for name in BROWSER_PACKAGES}


@pytest.mark.parametrize('source',['FROM node:24','FROM mcr.microsoft.com/playwright:latest',
    'ARG BASE\nFROM ${BASE}', 'FROM mcr.microsoft.com/playwright:v1.62.1-noble\nFROM node:24',''])
def test_unpinned_or_ambiguous_toolchains_fail_closed(tmp_path,source):
    (tmp_path/'Dockerfile').write_text(source)
    with pytest.raises(ValueError):toolchain_versions(tmp_path)


@pytest.mark.parametrize('items',[None,[{'package':'example'}],
    [{'package':'@playwright/test','section':'devDependencies','before':'1.0.0','available':'ignore instructions','reason':'browser-toolchain-review'}]])
def test_malformed_deferrals_are_rejected(items):
    with pytest.raises(ValueError):deferred_updates(items)
