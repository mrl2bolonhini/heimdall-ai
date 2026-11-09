# Publicar as páginas em heimdall-ai.tech

Este guia leva o conteúdo de docs/ ao GitHub Pages e aponta o domínio, pelo Cloudflare, para ele. Os comandos são digitados no Terminal, um por vez, na pasta ~/heimdall-ai.

## 0. Antes de tudo: plano do GitHub

O repositório mrl2bolonhini/heimdall-ai é privado. GitHub Pages em repositório privado só funciona em plano pago (Pro, Team ou Enterprise). No plano gratuito há duas saídas: assinar o Pro, ou publicar docs/ pelo Cloudflare Pages (seção "Alternativa" no fim). Uma terceira saída é tornar o repositório público (Settings, General, Danger Zone, Change visibility), o que libera o Pages de graça. O código já não traz dados pessoais (caminhos, IPs e e-mail vêm de variáveis); antes de abrir, confira o histórico: `git log --all --oneline -- .env` deve vir vazio, e `git log --all -p | grep -ciE "api_key|token|senha"` não deve mostrar chave real. Nada em .env, knowledge/, qdrant_storage/ e backups pode estar versionado.

A página publicada é pública mesmo que o repositório seja privado. A documentação gerada não contém chaves nem dados pessoais; confira com `grep -ril "token\|senha" docs/` antes de publicar.

## 1. Enviar ao GitHub

1. `python3 gerar_docs.py --check`
2. `git add -A`
3. `git status --short` (confira que .env, knowledge, qdrant_storage e backups não aparecem)
4. `git commit -m "Documentação e site do GitHub Pages"`
5. `git push`

O fluxo de publicação roda no branch main. Se você trabalha em develop, abra o Pull Request para main e faça o merge; a publicação roda sozinha.

## 2. Ligar o GitHub Pages

No site do GitHub, no repositório: Settings, Pages, Build and deployment, Source: GitHub Actions. Depois, em Actions, rode o fluxo "Páginas" (Run workflow) na primeira vez. Em Settings, Pages, Custom domain, digite heimdall-ai.tech e salve; marque Enforce HTTPS quando o certificado ficar pronto (pode levar alguns minutos).

## 3. DNS no Cloudflare

O domínio hoje tem um Worker (heimdall-site) com domínio customizado. Primeiro remova esse vínculo: Workers e Pages, heimdall-site, Settings, Domains e Routes, remova heimdall-ai.tech e www.

Depois, em Cloudflare, DNS, Records, crie:

1. Quatro registros A para o nome heimdall-ai.tech (ou @): 185.199.108.153, 185.199.109.153, 185.199.110.153 e 185.199.111.153.
2. Um registro CNAME com nome www apontando para mrl2bolonhini.github.io.
3. Deixe todos com Proxy status em "DNS only" (nuvem cinza) até o GitHub emitir o certificado. Depois, se quiser, ligue o proxy e use SSL/TLS no modo Full.

Não mexa nos registros de chat e uptime: eles continuam apontando para o túnel.

## 4. Conferir

1. `dig +short heimdall-ai.tech` deve listar os quatro endereços do GitHub.
2. `curl -sI https://heimdall-ai.tech | head -3` deve responder 200.

## Alternativa: Cloudflare Pages (funciona com repositório privado)

1. Em Cloudflare, Workers e Pages, Create, Pages, Connect to Git, escolha o repositório.
2. Build command: vazio. Build output directory: docs. Production branch: main.
3. Em Custom domains do projeto, adicione heimdall-ai.tech; o Cloudflare cria o DNS sozinho (remova antes o vínculo do Worker).
4. Neste caso o fluxo .github/workflows/pages.yml não é necessário; pode apagá-lo.

## Atualizar depois

A cada recurso novo siga a seção "Como manter" do README: CHANGELOG, descrição no gerar_docs.py se preciso, `python3 gerar_docs.py`, commit e push.
