# receitanet-cookie-renewer

Container Playwright headless que loga no ReceitaNet (Keycloak SSO) automaticamente e renova o cookie guardado numa credencial do n8n. Cron disparado pelo n8n a cada 3 dias, 03h BRT.

## ⚠️ Antes de qualquer coisa

**Nenhum valor real entra em arquivo versionado.** Sem token, sem senha, sem id de credencial, sem host de produção, sem telefone. Tudo vem de variável de ambiente — o `docker-compose.yml` só referencia `${VAR}`, e o `.env.example` documenta o formato sem preencher.

Antes de dar push, rode o gate:

```bash
./scripts/check-secrets.sh
```

Para que ele rode sozinho:

```bash
ln -sf ../../scripts/check-secrets.sh .git/hooks/pre-push
```

Se um segredo já tiver saído da máquina, **rotacionar é o que resolve** — tornar o repositório privado ou reescrever o histórico não invalida o que já foi copiado.

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
│  2. Login Keycloak (SSO do sistema)      │
│  3. Captura cookie da sessão             │
│  4. PATCH n8n /credentials/{id}          │
│  5. Alerta WhatsApp ao operador          │
└──────────────────────────────────────────┘
```

## Deploy no easypanel

### 1. Criar app

- **Type:** Docker Image / Dockerfile
- **Source:** este repo
- **Port:** 8080
- **Network:** mesma do n8n (`easypanel`)
- **Domain:** opcional, pode ficar interno só

### 2. Variáveis de ambiente (Settings → Environment)

Use o [`.env.example`](.env.example) como lista de referência — todas as variáveis de lá precisam estar preenchidas no painel. Não há mais nenhum default embutido no código.

| Variável | Obrigatória | O que é |
|---|---|---|
| `RECEITANET_USER` / `RECEITANET_PASS` | sim | credenciais do sistema alvo |
| `N8N_API_URL` | sim | base da public API, terminando em `/api/v1` |
| `N8N_API_KEY` | sim | n8n → Settings → API → Show key |
| `N8N_CREDENTIAL_ID` | sim | id da credential que guarda o cookie |
| `RENEW_AUTH_TOKEN` | sim | `openssl rand -hex 32` |
| `WEBHOOK_ALERTA_URL` | não | endpoint de envio do gateway de WhatsApp |
| `UAZAPI_TOKEN_ALERTA` | não | token do gateway |
| `ALERTA_WHATSAPP_DESTINO` | não | número que recebe alertas (só dígitos, com DDI) |
| `HEADLESS` / `PORT` | não | default `true` / `8080` |

Sem as três de alerta, o alerta é apenas logado — a renovação continua funcionando.

### 3. Deploy + smoke test

```bash
curl -X POST https://<host>/renew -H "X-Renew-Token: <RENEW_AUTH_TOKEN>"
```

Esperado:
- HTTP 200 com `{"ok":true,"cookie_len":...}`
- O número em `ALERTA_WHATSAPP_DESTINO` recebe "✅ Cookie ReceitaNet renovado"
- A credential apontada por `N8N_CREDENTIAL_ID` é atualizada com o novo cookie

### 4. Cron n8n

Criar workflow `RenovarCookieReceitaNet`:
- **Schedule Trigger:** cron `0 3 */3 * *` (a cada 3 dias, 03h BRT) — Timezone `America/Sao_Paulo`
- **HTTP Request:** POST `http://receitanet-cookie-renewer:8080/renew` (mesma network easypanel) com header `X-Renew-Token: <token>`
- **Code:** parseia resposta; se falhar, manda alerta extra

## Manutenção

- **Senha do sistema mudou** → atualiza `RECEITANET_PASS` no easypanel, redeploy automático.
- **Token da API do n8n rotacionou** → atualiza `N8N_API_KEY`.
- **Token do gateway de alerta rotacionou** → atualiza `UAZAPI_TOKEN_ALERTA`.
- **Layout do ReceitaNet mudou** → provavelmente o seletor `input[name="username"]` ou o botão `#kc-login`. Olha o log do container, atualiza o seletor no `renew.py`, roda o gate, push.

## Debug local

```bash
cp .env.example .env   # preencha; o .env é ignorado pelo git
docker-compose up --build
docker-compose exec receitanet-cookie-renewer python renew.py
```

Para ver o browser (não headless):
```bash
HEADLESS=false python renew.py
```

(Requer Playwright local: `pip install playwright && playwright install chromium`.)
