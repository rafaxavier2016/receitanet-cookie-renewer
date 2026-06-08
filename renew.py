"""
Auto-renovador de cookie ReceitaNet via Playwright headless.

Fluxo:
1. Abre Chromium headless
2. Navega pra https://sistema.receitanet.net/ → redireciona pro Keycloak login
3. Preenche username + password do env
4. Submete form, aguarda redirect de volta pro sistema
5. Captura cookies da sessão
6. Atualiza credential `ZLghSJcWQTLEcuQd` no n8n via API
7. Reporta status via webhook opcional (alerta WhatsApp)

Env vars obrigatórios:
- RECEITANET_USER         — login do ReceitaNet
- RECEITANET_PASS         — senha do ReceitaNet
- N8N_API_URL             — ex: https://n8n-n8n.3ccrdq.easypanel.host/api/v1
- N8N_API_KEY             — token da public API do n8n
- N8N_CREDENTIAL_ID       — id da credential do cookie (default: ZLghSJcWQTLEcuQd)

Env vars opcionais:
- WEBHOOK_ALERTA_URL      — URL pra POST {sucesso, cookie, erro} (ex: https://automacoes2026.uazapi.com/send/text)
- UAZAPI_TOKEN_ALERTA     — token do UazAPI RJ-NET (4406) pra alertas
- RAFAEL_WHATSAPP         — número do Rafael (553197403925)
- HEADLESS                — "false" pra debug visual (default "true")

Uso:
    python renew.py            # roda 1 vez
    python renew.py --serve    # roda como HTTP server na porta 8080 (cron externo dispara)
"""
import os, sys, json, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

RECEITANET_USER = os.environ.get('RECEITANET_USER','').strip()
RECEITANET_PASS = os.environ.get('RECEITANET_PASS','').strip()
N8N_API_URL = os.environ.get('N8N_API_URL','').rstrip('/')
N8N_API_KEY = os.environ.get('N8N_API_KEY','').strip()
N8N_CREDENTIAL_ID = os.environ.get('N8N_CREDENTIAL_ID','ZLghSJcWQTLEcuQd').strip()
WEBHOOK_ALERTA_URL = os.environ.get('WEBHOOK_ALERTA_URL','').strip()
UAZAPI_TOKEN_ALERTA = os.environ.get('UAZAPI_TOKEN_ALERTA','').strip()
RAFAEL_WHATSAPP = os.environ.get('RAFAEL_WHATSAPP','553197403925').strip()
HEADLESS = os.environ.get('HEADLESS','true').lower() != 'false'


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def alertar_rafael(texto):
    """Manda mensagem ao Rafael via UazAPI RJ-NET (4406)."""
    if not (WEBHOOK_ALERTA_URL and UAZAPI_TOKEN_ALERTA):
        log(f"alerta skip (sem WEBHOOK_ALERTA_URL/UAZAPI_TOKEN_ALERTA): {texto[:100]}")
        return
    try:
        req = urllib.request.Request(WEBHOOK_ALERTA_URL, method='POST',
            data=json.dumps({'number': RAFAEL_WHATSAPP, 'text': texto}).encode('utf-8'),
            headers={'token': UAZAPI_TOKEN_ALERTA, 'Content-Type':'application/json'})
        urllib.request.urlopen(req, timeout=15).read()
        log(f"alerta enviado ({len(texto)} chars)")
    except Exception as e:
        log(f"alerta FAIL: {e}")


def atualizar_credential_n8n(cookie_value, allowed_domain='https://sistema.receitanet.net'):
    """Atualiza credential httpHeaderAuth no n8n com novo cookie."""
    if not (N8N_API_URL and N8N_API_KEY):
        raise RuntimeError("N8N_API_URL e N8N_API_KEY são obrigatórios")
    payload = {
        'name': 'Cookie',
        'value': cookie_value,
        'allowedDomains': allowed_domain,
    }
    req = urllib.request.Request(
        f"{N8N_API_URL}/credentials/{N8N_CREDENTIAL_ID}",
        method='PATCH',
        data=json.dumps({'data': payload}).encode('utf-8'),
        headers={'X-N8N-API-KEY': N8N_API_KEY, 'Content-Type': 'application/json'},
    )
    resp = urllib.request.urlopen(req, timeout=30).read()
    log(f"credential atualizada: {resp[:200].decode('utf-8',errors='replace')}")


def renovar():
    if not (RECEITANET_USER and RECEITANET_PASS):
        raise RuntimeError("RECEITANET_USER e RECEITANET_PASS são obrigatórios no env")

    log(f"iniciando renovação (user={RECEITANET_USER[:3]}***)")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = ctx.new_page()

        try:
            log("step 1: GET https://sistema.receitanet.net/")
            page.goto('https://sistema.receitanet.net/', wait_until='networkidle', timeout=30000)

            log(f"step 2: pagina atual = {page.url}")
            # Espera form de login do Keycloak (campo username)
            page.wait_for_selector('input[name="username"]', timeout=15000)

            log("step 3: preenchendo username + password")
            page.fill('input[name="username"]', RECEITANET_USER)
            page.fill('input[name="password"]', RECEITANET_PASS)

            log("step 4: submit form")
            with page.expect_navigation(wait_until='networkidle', timeout=30000):
                # Pode ser button#kc-login OU input[type=submit] OU button[type=submit]
                page.click('input[type="submit"], button[type="submit"], button[name="login"], #kc-login')

            log(f"step 5: pos-login URL = {page.url}")

            # Validar que NÃO ficou na página de login (login falhou)
            if 'auth.receitanet.net' in page.url and 'login' in page.url.lower():
                # Pode haver mensagem de erro
                erro_msg = ''
                try:
                    erro_el = page.query_selector('.kc-feedback-text, .alert-error, #input-error')
                    if erro_el:
                        erro_msg = erro_el.inner_text()[:200]
                except: pass
                raise RuntimeError(f"login falhou — ainda na pagina Keycloak: {erro_msg}")

            log("step 6: capturando cookies")
            cookies = ctx.cookies()
            sistema_cookies = [c for c in cookies if 'receitanet' in c.get('domain','').lower()]
            log(f"   {len(cookies)} cookies totais, {len(sistema_cookies)} do dominio receitanet")

            # O sincronizar-receitanet usa Cookie: PHPSESSID=...; outros — manda TODOS do dominio sistema.receitanet.net
            sistema_only = [c for c in cookies if c.get('domain','').endswith('sistema.receitanet.net') or c.get('domain','') == 'sistema.receitanet.net']
            cookie_header = '; '.join(f"{c['name']}={c['value']}" for c in sistema_only)

            if not cookie_header:
                raise RuntimeError(f"nenhum cookie do dominio sistema.receitanet.net retornado. Cookies: {[(c['name'],c['domain']) for c in cookies]}")

            log(f"step 7: cookie header montado ({len(cookie_header)} chars, {len(sistema_only)} cookies)")

            # Verifica que sessao funciona — GET /clientes deve devolver HTML (nao redirect pra login)
            log("step 8: validando sessao via GET /clientes")
            test_resp = page.goto('https://sistema.receitanet.net/clientes', wait_until='domcontentloaded', timeout=20000)
            if test_resp and test_resp.status >= 400:
                raise RuntimeError(f"sessao parece invalida — /clientes retornou {test_resp.status}")
            if '/login' in page.url or 'auth.receitanet.net' in page.url:
                raise RuntimeError(f"sessao parece invalida — /clientes redirecionou pra {page.url}")
            log(f"   /clientes OK (URL final = {page.url})")

            return cookie_header

        finally:
            browser.close()


def main():
    try:
        cookie = renovar()
        atualizar_credential_n8n(cookie)
        msg = f"✅ Cookie ReceitaNet renovado\n\nCookie ({len(cookie)} chars) salvo na credential n8n ZLghSJcWQTLEcuQd.\n\nPróxima renovação automática em 3 dias."
        alertar_rafael(msg)
        log("SUCESSO")
        return 0
    except Exception as e:
        log(f"FALHA: {e}")
        msg = f"🚨 *Falha na renovação automática do cookie ReceitaNet*\n\nErro: {str(e)[:400]}\n\nAção: renovar manualmente via Cookie-Editor enquanto investigo."
        alertar_rafael(msg)
        return 1


def serve():
    """Modo HTTP server — n8n cron chama POST /renew com header auth."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    AUTH_TOKEN = os.environ.get('RENEW_AUTH_TOKEN', 'change-me-via-env')

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != '/renew':
                self.send_response(404); self.end_headers(); return
            if self.headers.get('X-Renew-Token') != AUTH_TOKEN:
                self.send_response(401); self.end_headers(); return
            try:
                cookie = renovar()
                atualizar_credential_n8n(cookie)
                alertar_rafael(f"✅ Cookie ReceitaNet renovado ({len(cookie)} chars)")
                body = json.dumps({'ok': True, 'cookie_len': len(cookie)}).encode('utf-8')
                self.send_response(200)
            except Exception as e:
                alertar_rafael(f"🚨 Falha renovação cookie: {str(e)[:300]}")
                body = json.dumps({'ok': False, 'erro': str(e)}).encode('utf-8')
                self.send_response(500)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/health':
                self.send_response(200); self.end_headers(); self.wfile.write(b'ok'); return
            self.send_response(404); self.end_headers()

        def log_message(self, fmt, *args):
            log(f"http {fmt % args}")

    port = int(os.environ.get('PORT','8080'))
    log(f"server listening on :{port}")
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()


if __name__ == '__main__':
    if '--serve' in sys.argv:
        serve()
    else:
        sys.exit(main())
