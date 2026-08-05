#!/usr/bin/env bash
# Gate de verificação: barra segredo e dado pessoal antes de sair da máquina.
#
# Uso manual:   ./scripts/check-secrets.sh
# Como hook:    ln -sf ../../scripts/check-secrets.sh .git/hooks/pre-push
#
# Sai 1 (bloqueia) se achar algo. Falso positivo? Ajuste o padrão — não
# desligue o gate.
set -uo pipefail
cd "$(dirname "$0")/.."

FALHAS=0
aviso() { echo "  ✗ $1"; FALHAS=$((FALHAS+1)); }

# Arquivos rastreados, menos os que existem justamente pra documentar formato.
ARQUIVOS=$(git ls-files | grep -vE '^(\.env\.example|scripts/check-secrets\.sh)$' || true)
[ -z "$ARQUIVOS" ] && { echo "nada rastreado"; exit 0; }

echo "== gate de segredos =="

# 1. UUID solto = formato de token de API (UazAPI, entre outros)
if echo "$ARQUIVOS" | xargs grep -InE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' 2>/dev/null; then
  aviso "UUID literal — parece token de API"
fi

# 2. Chaves de provedores conhecidos
if echo "$ARQUIVOS" | xargs grep -InE '(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|sb_secret_[A-Za-z0-9_]+|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,})' 2>/dev/null; then
  aviso "chave de API / JWT literal"
fi

# 3. Telefone brasileiro literal (dado pessoal)
if echo "$ARQUIVOS" | xargs grep -InE "['\"]?55[1-9][0-9]{9,10}['\"]?" 2>/dev/null; then
  aviso "número de telefone literal"
fi

# 4. CPF / CNPJ
if echo "$ARQUIVOS" | xargs grep -InE '[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}|[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}' 2>/dev/null; then
  aviso "CPF ou CNPJ literal"
fi

# 5. Atribuição de segredo com valor preenchido (e não ${VAR})
if echo "$ARQUIVOS" | xargs grep -InE '(PASS|PASSWORD|SENHA|TOKEN|API_KEY|APIKEY|SECRET)[[:space:]]*[:=][[:space:]]*['\''"]?[A-Za-z0-9_-]{12,}' 2>/dev/null | grep -v '\${' ; then
  aviso "variável de segredo com valor literal — use \${VAR}"
fi

# 6. .env rastreado
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  aviso ".env está rastreado pelo git"
fi

if [ "$FALHAS" -gt 0 ]; then
  echo
  echo "BLOQUEADO: $FALHAS achado(s). Nada sai daqui com segredo dentro."
  exit 1
fi
echo "  ✓ limpo"
