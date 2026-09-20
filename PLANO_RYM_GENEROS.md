# Plano: géneros do Rate Your Music

Recolher o género de cada track a partir do Rate Your Music (RYM), sabendo à
partida que o RYM responde a automação com testes "I'm not a robot" constantes.

## O problema central

- O RYM **não tem API pública** e os ToS proíbem scraping.
- A defesa anti-bot é agressiva e em camadas: Cloudflare (cookie `cf_clearance`)
  mais um interstitial próprio de verificação ("are you a robot"). Clientes HTTP
  simples (`requests`/`httpx`) e bibliotecas não-oficiais (`rymscraper` e afins)
  são bloqueados quase de imediato. Não vale a pena tentar essa via.
- Consequência: ao contrário do harvest do Discogs, este harvest **nunca será
  unattended**. Será semi-assistido: corre num browser real e visível, e conta
  com o utilizador por perto para resolver os desafios quando aparecem.
- Toda a arquitetura abaixo existe para minimizar o número de pedidos — é a
  única métrica que interessa contra CAPTCHAs — e para garantir que nada do que
  já foi recolhido se perde ou se repete.

## Decisões de desenho

1. **Browser real, visível, com perfil persistente.** Playwright com
   `channel="chrome"` e `headless=False`, user-data-dir em
   `~/.config/spotidal/rym-profile/`. Os cookies (Cloudflare, sessão RYM)
   sobrevivem entre runs: cada run reutiliza a "reputação" do anterior, e o
   primeiro run serve para o utilizador fazer login no RYM à mão (opcional, mas
   uma sessão com histórico parece mais humana).
2. **Resolver releases, não tracks.** No RYM o género é atribuído ao release
   (álbum/single/EP), não à faixa. Deduplicar por `(artista, álbum)` antes de
   qualquer pedido: um álbum de 12 faixas custa 1 página, não 12. Isto reduz o
   volume de pedidos tipicamente 5–10×, e é o que torna a abordagem viável.
   Singles sem álbum caem na pesquisa pelo título da faixa, como já faz
   `_search_queries` no Discogs filler.
3. **Cache eterna.** Resultados (hits *e* misses) guardados para sempre em JSON,
   seguindo o precedente de `discogs_cache.json` em `genre.py`. Nunca refazer um
   pedido já feito; checkpoint a cada N chamadas.
4. **Pacing humano.** Delay aleatório de 10–25 s entre páginas, pausa longa
   (60–120 s) a cada ~20 páginas, zero concorrência. Orçamento de sessão
   (`--max-pages`, default ~80) e abort automático após 3 desafios num run —
   nesse ponto o site está de mau humor e insistir só queima reputação do IP.
5. **CAPTCHA = pausa para humano, nunca bypass.** Ao detetar o interstitial:
   `Text.warning(...)` + som de notificação (`view/sound.py`), polling a cada
   ~5 s até o utilizador resolver na janela visível, timeout de ~10 min, e se
   expirar: checkpoint e saída limpa com exit code próprio. Nenhuma tentativa de
   resolver o desafio programaticamente.
6. **Espelhar a arquitetura do harvest Discogs.** Novo módulo
   `spotidal/model/rym.py` com `RymClient` + `RymTaxonomyFiller`, análogos a
   `DiscogsClient`/`DiscogsTaxonomyFiller`. Mesmas convenções: escrita só em
   tabelas próprias (nunca `tracks.genre`, nunca tags de ficheiros), progresso
   na base de dados para ser seguro interromper, exit codes 0/2/3.

## Fases

### Fase 0 — spike manual (sem código de produção)

Abrir o Chrome via Playwright persistente e navegar à mão para 3–5 releases
conhecidos da biblioteca:

- confirmar o markup atual da página de release: primary genres, secondary
  genres, descriptors (historicamente `span.release_pri_genres` /
  `span.release_sec_genres` — **verificar, muda**);
- confirmar o markup da pesquisa de releases
  (`/search?searchterm=...&searchtype=l`);
- observar o interstitial "robot" na prática: URL, texto, e se a página volta ao
  normal sozinha depois de resolvido (isto define a deteção e o polling).

Resultado: seletores confirmados e comportamento do desafio documentado. Sem
isto não se escreve o parser.

### Fase 1 — schema (migração aditiva em `library.py`)

Estilo das migrações existentes (`CREATE TABLE IF NOT EXISTS` + versões em
`schema_migrations`):

- `rym_release(rym_release_id PK, track_id FK, rym_path TEXT, title, artist,
  year, confidence, match_method, is_selected, review_status, selection_method,
  created_at, updated_at)` — espelho de `discogs_release`; `rym_path`
  (ex. `/release/album/artista/titulo/`) é a identidade estável.
- `rym_release_genre(rym_release_id FK, name TEXT, kind TEXT CHECK(kind IN
  ('primary','secondary','descriptor')))` — vocabulário **separado** das tabelas
  `genre`/`style` do Discogs: são taxonomias diferentes e misturá-las polui o
  bucketing existente.
- `harvest_log`: hoje a PK é só `track_id`; sem alteração, o harvest do RYM
  herdaria os `unmatched` do Discogs e saltaria tracks à toa. Adicionar coluna
  `source TEXT NOT NULL DEFAULT 'discogs'` e recriar a tabela com PK
  `(track_id, source)`, preservando as linhas existentes.

### Fase 2 — `RymClient` (`spotidal/model/rym.py`)

- Wrapper sobre a API sync do Playwright; arranque lazy; contexto persistente.
- `search_release(artist, album)` → lista de candidatos (rym_path, título,
  artista, ano).
- `release_detail(rym_path)` → `{title, artist, year, primary_genres,
  secondary_genres, descriptors}`.
- `_goto(url)`: pacing (fase "decisões" acima), deteção de desafio, espera por
  humano, contagem de desafios por sessão.
- Cache JSON com hits e misses, flush periódico, análoga à do Discogs.
- Exceções `SiteBlocked` / `BudgetExhausted`, análogas a
  `ApiUnavailable` / `BudgetExhausted` de `genre.py`, para o loop poder parar
  com checkpoint em vez de martelar o site.

### Fase 3 — `RymTaxonomyFiller` (harvest loop)

- `selection_tracks()` / `all_tracks()` copiados do filler Discogs (seleção do
  utilizador primeiro, resto da biblioteca depois).
- Deduplicação por release: `(primeiro artista normalizado, álbum normalizado)`
  via `_normalize_match_text`; um release resolvido faz fan-out para todas as
  tracks desse par na biblioteca.
- `resolve()`: pesquisa → aceitar candidato com título/artista normalizados
  iguais (ou token-subset) e ano ±5, na filosofia dos checks `_weak_release`.
- `store()`: escreve **só** `rym_release` + `rym_release_genre`. Nunca
  `tracks.genre`, nunca tags — a mesma disciplina do harvest Discogs.
- Bookkeeping em `harvest_log` com `source='rym'`: `MAX_UNMATCHED_ATTEMPTS`,
  `--retry-unmatched`, falhas de site não incrementam tentativas.

### Fase 4 — CLI + menu

- `spotidal harvest rym [selection|all|<playlist>] [--retry-unmatched]
  [--max-pages N]`. `harvest` sem fonte continua Discogs — os cron/launchd
  existentes não partem.
- Exit codes coerentes com o harvest atual: `0` terminou, `2` site bloqueou ou
  desafio não resolvido, `3` orçamento de páginas esgotado.
- Entrada no menu Utils (grupo `GENRES_OPT`) que lança o mesmo caminho, com
  aviso explícito de "mantém a janela do browser visível; podes ter de resolver
  um desafio".
- Settings em `DEFAULTS` (`settings.py`): `rymMinDelay`, `rymMaxDelay`,
  `rymMaxPages`.

### Fase 5 — revisão e integração com os géneros finais

- Fila de revisão análoga a `review_playlist` em `discogs.py`: entram matches
  com confiança < 0.9 ou releases fracos; o utilizador aprova, troca por outro
  candidato, pesquisa à mão, ou classifica manualmente.
- **Decisão adiada de propósito:** como o vocabulário RYM alimenta
  `final_genre`/`track_genre_style` (provavelmente um mapeamento estilo
  `bucket_for()`). Só depois de vermos a distribuição real dos géneros RYM na
  biblioteca é que faz sentido desenhar esse mapa.

### Fase 6 — dependências e docs

- `pyproject.toml`: adicionar `playwright`; instalação do browser com
  `poetry run playwright install chrome`.
- `AGENTS.md`: novo item em "Hard requirements not declared in pyproject.toml"
  (browser real + perfil persistente).
- `docs/agents/`: `architecture.md` (novo módulo + boundary externo),
  `workflows.md` (harvest RYM semi-assistido), `data-model.md` (tabelas novas +
  coluna `source` no `harvest_log`), `status.md` (registo da adição).

## Verificação

Como sempre neste repo, não há testes: `poetry run python -m compileall -q
spotidal` para sintaxe, e um run real `spotidal harvest rym selection
--max-pages 10` contra a biblioteca verdadeira como teste de aceitação — com a
janela do browser à frente e pelo menos um desafio resolvido à mão para validar
o ciclo de pausa/retoma.

## Riscos assumidos

- Depende de markup e proteção que o RYM pode mudar a qualquer momento; a fase 0
  mitiga, mas não elimina. Se o RYM endurecer ao ponto de inviabilizar, o que já
  estiver em `rym_release`/`rym_release_genre` e na cache permanece válido.
- Volume realista: algumas centenas de releases únicos por biblioteca típica,
  ou seja algumas sessões de 30–60 min com o utilizador por perto — não uma
  noite de cron.
- ToS do RYM: aceitamos o risco inerente de um acesso automatizado pessoal e de
  baixo volume; o pacing e a cache existem precisamente para o manter baixo.
