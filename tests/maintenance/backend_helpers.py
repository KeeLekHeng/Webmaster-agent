def backend_proof():
    """Explicit fake CI attestation for controller boundary tests, not a live scan."""
    return {'mode':'real','cli_version':'2.119.0','postgres_major':17,
            'public_signup':'denied',
            **{k:'passed' for k in ('schema','rls','auth','storage','mfa_browser','uat_admin_browser','isolation','egress_probe','cleanup')},
            'images':{k:'sha256:'+'a'*64 for k in ('db','auth','rest','storage','kong')},
            'migrations':{'202610010001_example.sql':'b'*64},'seed_sha256':'c'*64}
