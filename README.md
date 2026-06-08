# receitanet-cookie-renewer

Container Playwright headless que loga no ReceitaNet (Keycloak SSO) automaticamente e renova o cookie da credencial n8n `ZLghSJcWQTLEcuQd`. Cron disparado pelo n8n a cada 3 dias 03h BRT.

## Arquitetura

```
┌──────────────────────────────────────────┐
│  n8n cron RenovarCookieReceitaNet (3d)   │
│  03h BRT → POST /renew (X-Renew-Token)   │
└──────────────┬───────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│  Container Playwright (porta 8080)       │
│  1. Chromium headless                    │
│  2. Login Keycloak (auth.receitanet.net) │
│  3. Captura cookie da sessão             │
│  4. PATCH n8n /credentials/{id}          │
│  5. Alerta WhatsApp via RJ-NET 4406      │
└──────────────────────────────────────────┘
```

## Deploy no easypanel

### 1. Criar app

- **Type:** Docker Image / Dockerfile
- **Source:** este repo (pasta `containers/receitanet-cookie-renewer/`)
- **Port:** 8080
- **Network:** mesma do n8n (`easypanel`)
- **Domain:** opcional, pode ficar interno só

### 2. Variáveis de ambiente (Settings → Environment)

Cola estas variáveis (substitua os `<...>`):

```
RECEITANET_USER=<seu usuario do ReceitaNet>
RECEITANET_PASS=<sua senha do ReceitaNet>
N8N_API_KEY=<copia do n8n: Settings → API → Show key>
RENEW_AUTH_TOKEN=<gera 1 token aleatorio: openssl rand -hex 32>
```

As outras (`N8N_API_URL`, `WEBHOOK_ALERTA_URL`, `UAZAPI_TOKEN_ALERTA`, `RAFAEL_WHATSAPP`, `N8N_CREDENTIAL_ID`, `HEADLESS`, `PORT`) já estão hardcoded no `docker-compose.yml` ou têm default razoável.

### 3. Deploy + Smoke test

Após deploy, dispara manualmente uma vez pra confirmar que loga OK:

```bash
curl -X POST https://<host>/renew -H "X-Renew-Token: <RENEW_AUTH_TOKEN>"
```

Esperado:
- HTTP 200 com `{"ok":true,"cookie_len":...}`
- WhatsApp do Rafael recebe "✅ Cookie ReceitaNet renovado"
- Credencial `ZLghSJcWQTLEcuQd` no n8n é atualizada com novo cookie

### 4. Cron n8n

Criar workflow `RenovarCookieReceitaNet`:
- **Schedule Trigger:** cron `0 3 */3 * *` (a cada 3 dias 03h BRT) — definir Timezone `America/Sao_Paulo`
- **HTTP Request:** POST `http://receitanet-cookie-renewer:8080/renew` (se mesma network easypanel) com header `X-Renew-Token: <token>`
- **Code:** parseia resposta, se falhar manda alerta extra

## Manutenção

### Quando senha mudar

Atualiza a env var `RECEITANET_PASS` no easypanel → redeploy auto.

### Quando o token API n8n rotacionar

Atualiza `N8N_API_KEY`.

### Quando ReceitaNet mudar layout

Provavelmente o seletor `input[name="username"]` ou o botão `#kc-login` muda. Olha o log do container, atualiza o seletor no `renew.py`, push.

## Debug local

```bash
docker-compose up --build
docker-compose exec receitanet-cookie-renewer python renew.py
```

Para ver o browser (não headless):
```bash
HEADLESS=false python renew.py
```

(Requer Playwright instalado localmente: `pip install playwright && playwright install chromium`.)
