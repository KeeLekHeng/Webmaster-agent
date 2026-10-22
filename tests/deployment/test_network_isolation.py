from pathlib import Path
import runpy

import pytest


check_policy = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'deploy/smoke.py'))['assert_socket_policy']


class Socket:
    def __init__(self, allow_ephemeral=False, allow_listen=False):
        self.allow_ephemeral = allow_ephemeral
        self.allow_listen = allow_listen

    def __enter__(self): return self
    def __exit__(self, *args): pass

    def bind(self, address):
        if self.allow_ephemeral and address[1] == 0:
            return
        raise PermissionError('denied')

    def listen(self, backlog):
        if not self.allow_listen:
            raise PermissionError('denied')


def test_checks_ipv4_ipv6_tcp_udp_ephemeral_fixed_and_listen():
    assert check_policy(lambda *args: Socket()) == 9


@pytest.mark.parametrize('allowed', ['ephemeral', 'listen'])
def test_rejects_incomplete_socket_policy(allowed):
    with pytest.raises(RuntimeError, match='not blocked'):
        check_policy(lambda *args: Socket(allow_ephemeral=allowed=='ephemeral', allow_listen=allowed=='listen'))
