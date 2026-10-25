#!/usr/bin/env bash
# Create (or re-use) the Platinum audit application on Coolify through its REST API, set its environment,
# and trigger the first deployment. Idempotent on name.
#
# Required env:
#   COOLIFY_URL      e.g. http://coolify.jbacteam.com:8000
#   COOLIFY_TOKEN    API token (Coolify → Keys & Tokens → API tokens). Never commit it.
#   GIT_REPO         public:  https://github.com/<org>/<repo>
#                    private: git@github.com:<org>/<repo>.git  (with PRIVATE_KEY_UUID — recommended, the repo holds business docs)
#   DASH_PASSWORD    password for the dashboard (HTTP Basic, user "admin", ASCII only)
# Optional env:
#   PRIVATE_KEY_UUID uuid of the Coolify SSH key added to the GitHub repo as a read-only deploy key → uses /applications/private-deploy-key
#   GIT_BRANCH=main  APP_NAME=platinum-audit  PROJECT_NAME="Platinum Audit"  DOMAIN=https://audit.jbacteam.com
#   BOT_TOKEN OWNER_CHAT_ID TG_API_ID TG_API_HASH TG_SESSION HASHTAG_ENFORCED_FROM
set -euo pipefail

: "${COOLIFY_URL:?set COOLIFY_URL}"; : "${COOLIFY_TOKEN:?set COOLIFY_TOKEN}"; : "${GIT_REPO:?set GIT_REPO}"; : "${DASH_PASSWORD:?set DASH_PASSWORD}"
GIT_BRANCH="${GIT_BRANCH:-main}"; APP_NAME="${APP_NAME:-platinum-audit}"; PROJECT_NAME="${PROJECT_NAME:-Platinum Audit}"
API="$COOLIFY_URL/api/v1"
auth=(-H "Authorization: Bearer $COOLIFY_TOKEN" -H "Accept: application/json" -H "Content-Type: application/json")
# `py -c CODE` runs inline code with stdin available for JSON; `py -` reads the program from a heredoc
py() { python3 "$@" 2>/dev/null || python "$@"; }

echo "== server"
SERVER_UUID=$(curl -sS "${auth[@]}" "$API/servers" | py -c 'import json,sys; print(json.load(sys.stdin)[0]["uuid"])')
echo "server: $SERVER_UUID"

echo "== project"
PROJECT_UUID=$(curl -sS "${auth[@]}" "$API/projects" | py -c "import json,sys
for p in json.load(sys.stdin):
    if p['name']=='$PROJECT_NAME': print(p['uuid'])")
if [ -z "$PROJECT_UUID" ]; then
  PROJECT_UUID=$(curl -sS "${auth[@]}" -X POST "$API/projects" -d "{\"name\":\"$PROJECT_NAME\",\"description\":\"Telegram ad-post audit (Platinum Club MM)\"}" | py -c 'import json,sys; print(json.load(sys.stdin)["uuid"])')
  echo "created project $PROJECT_UUID"
else
  echo "project exists $PROJECT_UUID"
fi

echo "== application"
APP_UUID=$(curl -sS "${auth[@]}" "$API/applications" | py -c "import json,sys
for a in json.load(sys.stdin):
    if a.get('name')=='$APP_NAME': print(a['uuid'])")
if [ -z "$APP_UUID" ]; then
  BODY=$(cat <<JSON
{"project_uuid":"$PROJECT_UUID","server_uuid":"$SERVER_UUID","environment_name":"production",
 "git_repository":"$GIT_REPO","git_branch":"$GIT_BRANCH","build_pack":"dockerfile","dockerfile_location":"/Dockerfile",
 "ports_exposes":"8000","name":"$APP_NAME","description":"Platinum Club MM Telegram audit",
 "health_check_enabled":true,"health_check_path":"/healthz","instant_deploy":false
 ${DOMAIN:+,\"domains\":\"$DOMAIN\"}${PRIVATE_KEY_UUID:+,\"private_key_uuid\":\"$PRIVATE_KEY_UUID\"}}
JSON
)
  ENDPOINT="applications/public"; [ -n "${PRIVATE_KEY_UUID:-}" ] && ENDPOINT="applications/private-deploy-key"
  RESP=$(curl -sS "${auth[@]}" -X POST "$API/$ENDPOINT" -d "$BODY")
  echo "$RESP"
  APP_UUID=$(echo "$RESP" | py -c 'import json,sys; print(json.load(sys.stdin)["uuid"])')
  echo "created application $APP_UUID"
else
  echo "application exists $APP_UUID"
fi

echo "== environment variables"
envjson=$(py - <<'PY'
import json, os
keys = ["DASH_PASSWORD","BOT_TOKEN","OWNER_CHAT_ID","TG_API_ID","TG_API_HASH","TG_SESSION","HASHTAG_ENFORCED_FROM"]
data = [{"key":"DB_PATH","value":"/data/audit.db","is_preview":False},{"key":"AUDIT_TZ","value":"Asia/Yangon","is_preview":False},
        {"key":"DASH_USER","value":"admin","is_preview":False}]
for k in keys:
    v = os.environ.get(k)
    if v: data.append({"key":k,"value":v,"is_preview":False})
print(json.dumps({"data":data}))
PY
)
curl -sS "${auth[@]}" -X PATCH "$API/applications/$APP_UUID/envs/bulk" -d "$envjson" | head -c 400; echo

echo "== persistent storage for /data (SQLite)"
curl -sS "${auth[@]}" -X POST "$API/applications/$APP_UUID/storages" \
  -d '{"type":"persistent","name":"audit-data","mount_path":"/data"}' | head -c 300 || true
echo
echo "   (if the storage call above was rejected, add a Volume Mount in the Coolify UI: name audit-data, destination /data)"

echo "== deploy"
curl -sS "${auth[@]}" -X POST "$API/deploy?uuid=$APP_UUID&force=false" | head -c 400; echo
echo "application uuid: $APP_UUID — watch the build in Coolify, then open the FQDN /healthz"
