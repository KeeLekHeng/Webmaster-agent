"""Administrator-invoked sandbox smoke test. No credentials, API calls or sends."""
import json
import errno
import os
from pathlib import Path
import socket
import sqlite3


def assert_socket_policy(factory=socket.socket):
    checks = 0
    for family, address in ((socket.AF_INET, '0.0.0.0'), (socket.AF_INET6, '::')):
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            for port in (0, 49152):
                try:
                    server = factory(family, kind)
                except OSError as exc:
                    if family == socket.AF_INET6 and exc.errno == errno.EAFNOSUPPORT:
                        continue
                    raise
                with server:
                    try:
                        server.bind((address, port))
                    except PermissionError:
                        checks += 1
                    else:
                        raise RuntimeError('Socket binding was not blocked')
    # listen() can implicitly allocate a port even without a user-space bind().
    with factory(socket.AF_INET, socket.SOCK_STREAM) as server:
        try:
            server.listen(1)
        except PermissionError:
            checks += 1
        else:
            raise RuntimeError('Socket listening was not blocked')
    return checks


def main():
    import resource
    from guardian.workflows.audit import build_graph
    from guardian.workflows.period_review import run_review
    from guardian.telegram.service import OwnerBot

    assert os.getuid() != 0
    assert not os.access('/opt/sisweb', os.F_OK)
    assert not os.access('/home/deploy', os.F_OK)
    assert not os.access('/etc/guardian/guardian.env', os.F_OK)
    assert Path('/app/config/sites.json').is_file()
    assert os.getenv('AGENT_ENABLED') == 'false'
    assert os.getenv('GUARDIAN_TELEGRAM_ENABLED') == 'false'
    assert not any(os.getenv(k) for k in ('ANTHROPIC_API_KEY','GUARDIAN_GITHUB_READ_TOKEN','GUARDIAN_GITHUB_WRITE_TOKEN'))
    checks = assert_socket_policy()
    socket.getaddrinfo('estateplanning.com.my', 443, type=socket.SOCK_STREAM)
    probe = Path('/work/data/sandbox-smoke.sqlite3')
    probe.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(probe) as db:
        db.execute('CREATE TABLE IF NOT EXISTS checks(checked INTEGER)')
    filesystem = os.statvfs('/work')
    assert filesystem.f_blocks * filesystem.f_frsize <= 512 * 1024 * 1024
    print(json.dumps({'sandbox':'passed','peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      'dns':'resolved','public_bind':'blocked','socket_denial_checks':checks,
                      'production_paths':'absent','state_filesystem_mib':512}),flush=True)


if __name__ == '__main__':
    main()
