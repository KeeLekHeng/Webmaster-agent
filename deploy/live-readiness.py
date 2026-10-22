"""Bounded administrator-started checks; no Telegram send or repository writes."""
import json
import os
from pathlib import Path

from guardian.core.models import SiteConfig
from guardian.core.network import Transport
from guardian.integrations.google_auth import search_console_access
from guardian.telegram.service import OwnerBot
from guardian.workflows.period_review import run_review

config=SiteConfig.model_validate(json.loads(Path('/app/config/sites.json').read_bytes())['estateplanning'])
response=Transport(config).get(config.base_url.rstrip('/')+'/')
assert response.status==200
access=search_console_access()
assert access.status=='refreshed' and access.token
bot=OwnerBot('estateplanning',config)
assert bot.store.authorize(bot.bot_id,bot.settings.chat_id) is None
review=run_review({'site_id':'estateplanning','config':config,'property_name':os.environ['GUARDIAN_GSC_PROPERTY'],
                   'days':14,'include_queries':True,'mode':'claude','model':os.environ['GUARDIAN_MODEL'],
                   'output':'reports','lighthouse_paths':[str(p) for p in Path('data/performance/estateplanning').glob('*.json')]},progress=None)
report=review['report']
assert report.status=='complete' and report.analysis.status in {'complete','skipped'}
print(json.dumps({'website_http':200,'google_refresh':'verified','telegram_identity_and_pairing':'verified',
                  'search_collection':report.status,'claude_analysis':report.analysis.status,'report_run_id':report.run_id,
                  'message_sent':False,'repo_write_credentials_present':bool(os.getenv('GUARDIAN_GITHUB_WRITE_TOKEN'))}),flush=True)
assert not os.getenv('GUARDIAN_GITHUB_WRITE_TOKEN')
