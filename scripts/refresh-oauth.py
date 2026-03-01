#!/usr/bin/env python3
"""
Host-side OAuth token refresher for Capuchin bots.
Runs refresh-token.py inside corp-admin, then propagates to all instances.
"""
import json, time, os, subprocess, sys

BASE = '/opt/capuchin/repo/engine/instances'
OAUTH_PATH = f'{BASE}/admin/openclaw_data/oauth/anthropic-oauth.json'
INSTANCES = ['admin', 'nikita', 'dmitry', 'vasily']

def log(msg):
    print(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {msg}', flush=True)

# Проверяем нужно ли обновлять (меньше 2 часов до истечения)
try:
    with open(OAUTH_PATH) as f:
        oauth = json.load(f)
    exp = int(oauth['expiresAt']) / 1000
    remaining = exp - time.time()
    log(f'Token expires in {remaining/3600:.1f}h')
    if remaining > 2 * 3600 and '--force' not in sys.argv:
        log('No refresh needed')
        sys.exit(0)
except Exception as e:
    log(f'Could not read oauth: {e}')
    sys.exit(1)

# Обновляем через admin контейнер
log('Refreshing via corp-admin...')
result = subprocess.run(
    ['docker', 'exec', 'corp-admin', 'python3',
     '/home/node/.openclaw/oauth/refresh-token.py', '--force'],
    capture_output=True, text=True
)
if result.returncode != 0:
    log(f'REFRESH FAILED: {result.stderr}')
    sys.exit(1)
log(f'Refreshed OK')

# Читаем новый токен
with open(OAUTH_PATH) as f:
    oauth = json.load(f)
TOKEN = oauth['accessToken']
exp = int(oauth['expiresAt']) / 1000
log(f'New token: {TOKEN[:20]}... expires in {(exp-time.time())/3600:.1f}h')

# Обновляем auth-profiles.json всех инстансов
profile = {
  'version': 1,
  'profiles': {
    'anthropic:default': {
      'type': 'token',
      'provider': 'anthropic',
      'token': TOKEN
    }
  },
  'lastGood': {'anthropic': 'anthropic:default'},
  'usageStats': {
    'anthropic:default': {
      'lastUsed': int(time.time() * 1000),
      'errorCount': 0
    }
  }
}

for inst in INSTANCES:
    path = f'{BASE}/{inst}/openclaw_data/agents/main/agent/auth-profiles.json'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(profile, f, indent=2)
    os.chmod(path, 0o600)
    log(f'{inst}: auth-profiles updated')

log('Done')
