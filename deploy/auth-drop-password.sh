#!/usr/bin/env bash
# Снять basic_auth с app.kalita.tech (вход только кошельком). Запускать, когда в state/users.json есть admin.
set -u; C=/etc/caddy/Caddyfile
python3 - <<'PY'
import re; p='/etc/caddy/Caddyfile'; s=open(p).read()
new=re.sub(r'(app\.kalita\.tech \{\n)\tbasic_auth \{\n[^}]*\}\n', r'\1', s)
open(p+'.bak-auth','w').write(s); open(p,'w').write(new); print('изменён' if new!=s else 'basic_auth не найден')
PY
caddy validate --config $C --adapter caddyfile && systemctl reload caddy && echo "пароль снят" || { cp $C.bak-auth $C; echo "ошибка — откат"; exit 1; }
