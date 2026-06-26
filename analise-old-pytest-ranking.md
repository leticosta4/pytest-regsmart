# pytest-ranking — Documentação Detalhada

## Visão Geral

**pytest-ranking** é um plugin pytest que implementa **Regression Test Prioritization (RTP)** para acelerar a detecção de falhas em regressão. Ele reordena a execução dos testes para que os mais propensos a falhar executem primeiro, baseando-se em três heurísticas combináveis:

1. **Testes mais rápidos primeiro** (peso `1-0-0`, padrão)
2. **Testes que falharam recentemente primeiro** (peso `0-1-0`)
3. **Testes relacionados a mudanças no código** (peso `0-0-1`)

O plugin foi criado por Runxiang Cheng, Kaiyao Ke e Darko Marinov (University of Illinois), apresentado no FSE Companion 2025, e avaliado em **4.308 builds de 14 projetos open-source** no GitHub Actions CI.

---

## Arquitetura do Projeto

```
src/pytest_ranking/
├── __init__.py            # Pacote vazio
├── const.py               # Constantes, defaults, enum LEVEL
├── change_tracker.py      # changeTracker: hasheia .py, detecta delta, similaridade textual
├── rank.py                # get_test_group() + get_ranking(): agrega scores por nível
└── plugin.py              # RTPRunner (classe principal), hooks pytest, compute_test_features
```

### Quatro Componentes Principais (artigo §2.1)

O artigo define **quatro componentes** que interagem com o core do pytest, conforme ilustrado na **Figura 1** (página 1090):

```
                Pytest                          pytest-ranking
           ┌──────────────┐           ┌──────────────────────────┐
           │  Collect Tests│──(1)──▶  │         Ranker           │
           │              │◀──(2)──  │                          │
           │  Execute Tests│──(3)──▶  │         Monitor          │
           │              │          │                          │
           │  Pytest Cache │◀──(5)──  │        Extractor         │
           │              │          │                          │
           │  Print Summary│◀──(7)──  │         Reporter         │
           └──────────────┘           └──────────────────────────┘
```

**Fluxo numerado conforme a Figura 1:**

1. **(1)** Pytest fornece a lista de testes coletados ao **Ranker**
2. **(2)** Ranker devolve a lista priorizada para o Pytest executar
3. **(3)** Conforme cada teste termina, Pytest chama o **Monitor** com um objeto `TestReport` (duração, resultado)
4. **(4)** **Monitor** apenas acumula os `TestReport` em memória (lista no `RTPRunner`) — sem processamento para minimizar overhead
5. **(5)** Quando toda a suite termina, o **Extractor** processa os relatórios e salva dados no cache do pytest
6. **(6)** No próximo TSR, o **Ranker** carrega os dados cacheados para priorizar
7. **(7)** Ao final, o **Reporter** adiciona um sumário ao terminal do pytest com configuração e overhead

### Fluxo de Execução Detalhado

1. `pytest_configure` → instancia `RTPRunner` (contém os 4 componentes) e registra no `pluginmanager`
2. `pytest_report_header` → **Reporter** exibe configurações se `--rank` ativo
3. `changeTracker.__init__` → hasheia todos `*.py` e computa delta (arquivos alterados) — usado pelo **Ranker**
4. `pytest_collection_modifyitems` → **Ranker** valida replay+random, chama `run_rtp(items)` para reordenar
5. `pytest_runtest_logreport` → **Monitor** captura `TestReport` (não-skipped, `when=="call"`)
6. `pytest_sessionfinish` → **Extractor** persiste `last_durations` e `num_runs_since_fail` no cache
7. `pytest_terminal_summary` → **Reporter** exibe métricas de overhead

### Armazenamento de Dados

Toda a persistência usa o **cache interno do pytest** (`config.cache`), armazenado em `.pytest_cache/v/pytest_ranking_data/`:

| Chave | Conteúdo |
|---|---|
| `file_hashes` | SHA1 de cada `*.py` no projeto |
| `change_similarity` | Interseção de tokens entre nodeid do teste e paths alterados |
| `last_durations` | Último tempo de execução (`round(duration, 3)`) por nodeid |
| `num_runs_since_fail` | Nº de execuções desde a última falha (limitado por `--rank-hist-len`) |

---

## Parâmetros de Entrada

### Linha de comando / addopts

| Flag | Tipo | Default | Descrição |
|---|---|---|---|
| `--rank` | flag | `False` | Ativa o plugin |
| `--rank-weight` | string `"A-B-C"` | `"1-0-0"` | Pesos para tempo, falha, similaridade (normalizados p/ soma=1) |
| `--rank-level` | `put` / `function` / `module` / `dir` | `"put"` | Nível de agrupamento para reordenação |
| `--rank-hist-len` | int | `50` | Máximo de execuções registradas desde última falha |
| `--rank-seed` | int | `0` | Semente para ordem aleatória |
| `--rank-replay` | path | `None` | Arquivo com ordem explícita de testes (1 ID por linha) |

### Config file (pytest.ini)

```ini
[pytest]
rank_weight = 0-1-0
rank_level = module
rank_hist_len = 30
rank_seed = 42
```

CLI não-default sobrescreve `pytest.ini` (`RTPRunner.parse_*()`).

---

## Parâmetros de Saída

### Cabeçalho (antes da execução)

```
Using --rank-weight=1-0-0
Using --rank-level=put
Using --rank-hist-len=50
Using --rank-seed=0
Using --rank-replay=None
```

### Sumário (após execução)

```
=== pytest-ranking summary info ===
Number of changed Python files:              3
Time to compute test-change similarity (s):  0.00087
Time to reorder tests (s):                   0.00036
Time to collect test features (s):           0.00046
```

---

## Níveis de Reordenação (LEVEL)

| Nível | Agrupamento | Exemplo (nodeid) |
|---|---|---|
| `put` | Cada parametrização individual | `test_file.py::TestClass::test_method[param1]` |
| `function` | Função de teste sem parâmetros | `test_file.py::TestClass::test_method` |
| `module` | Arquivo de teste | `test_file.py` |
| `dir` | Diretório | `tests/` |

O score de um grupo é a **média aritmética** dos scores individuais dos testes no grupo. Testes dentro do mesmo grupo seguem a ordem padrão do pytest.

---

## HOOKs do pytest Utilizados

Os hooks são a API do pytest que o plugin reimplementa para alterar o comportamento padrão ([55]). A tabela abaixo mapeia cada hook ao componente do artigo (§2.1) que o implementa:

| Hook | Componente | Localização | Finalidade |
|---|---|---|---|
| `pytest_addoption(parser)` | — | `plugin.py` | Registra `--rank`, `--rank-weight`, `--rank-level`, `--rank-hist-len`, `--rank-seed`, `--rank-replay` + 5 opções `addini()` |
| `pytest_configure(config)` | **Runner** | `plugin.py` (trylast) | Instancia `RTPRunner` e registra no `pluginmanager` ([49]) |
| `pytest_report_header(config)` | **Reporter** | `plugin.py` | Exibe configuração no cabeçalho se `--rank` ativo |
| `pytest_collection_modifyitems(items)` | **Ranker** ([50]) | `plugin.py` (trylast) | Valida replay+random, chama `run_rtp(items)` que reordena a lista |
| `pytest_runtest_logreport(report)` | **Monitor** ([51]) | `plugin.py` | Acumula `TestReport` dos testes (não-skipped, `when=="call"`) |
| `pytest_sessionfinish(session, exitstatus)` | **Extractor** | `plugin.py` | Persiste `last_durations` e `num_runs_since_fail` no cache |
| `pytest_terminal_summary(terminalreporter, exitstatus, config)` | **Reporter** ([52]) | `plugin.py` | Exibe overhead: tempo de similaridade, reordenação, coleta |

---

## Etapas de Coleta (Feature Collection)

### 1. changeTracker.get_delta() — ao iniciar

- Varre todos `**/*.py` abaixo de `rootpath`
- Calcula SHA1 de cada arquivo
- Compara com hashes salvos no cache (`file_hashes`)
- Se houve mudança, tokeniza o path do arquivo e adiciona ao conjunto `delta`
- Salva hashes atualizados

### 2. compute_test_suite_similarity(items) — durante run_rtp()

- Para cada `item`, tokeniza `item.nodeid`
- Calcula `|delta ∩ tokens(item.nodeid)|` (interseção de conjuntos)
- Salva em cache (`change_similarity`)

### 3. load_feature(feature_name, items, reverse) — durante run_rtp()

- Carrega do cache: `last_durations` (reverse=True), `num_runs_since_fail` (reverse=True), `change_similarity` (reverse=False)
- Aplica `min_max_normalization` → valores em [0,1]
- Se `reverse=True`, transforma para `1 - valor` (menor é melhor vira maior é melhor)

### 4. compute_test_features() — ao final da sessão

- Atualiza `last_durations[nodeid]` com `report.duration` de cada teste
- Atualiza `num_runs_since_fail[nodeid]`: 0 se falhou, `min(hist_len, valor_anterior + 1)` se passou

---

## Algoritmo de Ranqueamento

### Cálculo do Score Individual

```
score(item) = -(w_t * norm_time + w_f * norm_fail + w_r * norm_rel)

onde:
  w_t + w_f + w_r = 1 (após normalização)
  norm_time   = 1 - min_max_normalize(last_durations[nodeid])
  norm_fail   = 1 - min_max_normalize(num_runs_since_fail[nodeid])
  norm_rel    =     min_max_normalize(change_similarity[nodeid])

Menor score → executado antes
```

### Agregação por Grupo

```
group_score(grupo) = mean(score(item) para todo item no grupo)
rank(item) = posição ordenada por (group_score, init_order)
```

### Ordenação Final

1. Testes com `@pytest.mark.order` ou `@pytest.mark.dependency` (OD) são mantidos no início, na ordem original
2. Testes sem OD são ordenados por `rank.get(nodeid, 0)` e depois `init_order` (desempate)
3. `items[:] = od_items + nod_items` (substitui a lista in-place)

### Modos Especiais

- **Replay** (`--rank-replay`): scores = posição no arquivo; ignora pesos
- **Aleatório** (`--rank-weight=0-0-0`): scores = `random.random()`; pre-sort por `nodeid` para compatibilidade com xdist
- Erro se `--rank-replay` + `--rank-weight=0-0-0`

---

## Detecção de Mudanças (changeTracker)

```python
changeTracker.__init__(pytest_config)
├── get_all_file_paths()    -> glob("**/*.py", recursive=True)
├── get_hash(file_path)     -> hashlib.sha1(file.read()).hexdigest()
├── get_delta()             -> compara hashes, tokeniza paths alterados
└── compute_test_suite_similarity(items) -> interseção tokens
```

`tokenize(string)` usa `re.findall(r'[a-zA-Z0-9]+', string.lower())` — extrai tokens alfanuméricos em lowercase.

Exemplo: path `src/utils/helper.py` → tokens `{"src", "utils", "helper", "py"}`.

---

## Comunicação com o Ecossistema pytest

### Descoberta Automática

```python
entry_points={
    'pytest11': ['pytest_ranking = pytest_ranking.plugin'],
}
```

### Compatibilidade com pytest-xdist

- Pre-sort dos items por `nodeid` antes de aplicar `random.seed()` para garantir mesma ordem em todos workers
- Reordenação ocorre antes da distribuição (hook `pytest_collection_modifyitems`)

### Respeito a Dependências de Ordem

```python
if item.get_closest_marker('order') or item.get_closest_marker('dependency'):
    od_items.append(item)
else:
    nod_items.append(item)
```

Testes com `@pytest.mark.order(n)` ou `@pytest.mark.dependency(...)` executam primeiro, na ordem original.

### Plugins Potencialmente Conflitantes

`--ff` (pytest), `pytest-randomly`, `pytest-random-order`, `pytest-reverse` — usam o mesmo hook `pytest_collection_modifyitems`.

---

## Experimento e Avaliação (artigo FSE Companion 2025)

### Pipeline de Seleção de Projetos (§4.1)

Processo em cascata partindo dos 2.500 projetos mais baixados do PyPI em 2023:

| Etapa | Filtro | Projetos Restantes |
|---|---|---|
| 1 | Top 2500 downloads PyPI 2023 | 2.500 |
| 2 | Exclui sem URL GitHub, Python version ou pytest version no metadata | 315 |
| 3 | Exclui sem CI nos commits recentes ou clone >1 min | 122 |
| 4 | Mantém >1.000 estrelas + ≥1 TSR com falha na branch default | 58 |
| 5 | Inspeção manual dos top 40; verifica se build passa em ubuntu-latest/Python3 com TSR >45s | **12** |
| 6 | Extra: busca nos top 50.000 projetos que usam plugins de ordem aleatória, inspeciona 19 | +**2** |
| **Total** | | **14 projetos** |

### Dataset

- **14 projetos open-source** que usam pytest e GitHub Actions
- **27.224 builds** coletados via API do GitHub (TSR builds completos, Jan–Dez 2024)
- **718 commits selecionados** para reexecução → **4.308 TSRs** (6 ordens cada)
- Builds não-TSR (release, docs) e incompletos (cancelled, timed_out, skipped) removidos

### Métrica

- **APFDc** (Average Percentage of Faults Detected per Cost) — normalizada em [0, 1]
  - `APFDc = ∑custos_TF / (num_bugs * ∑todas_durações)` onde `custo_TF(pos) = ∑duração[pos-1:] - duração[pos-1]/2`
- Dois mapeamentos falha→bug: `sameBug` (many-to-one) e `uniqueBug` (one-to-one); produzem resultados similares
- Comparação contra: ordem default e ordem aleatória (seed mediana)

### Análise de Testes Flaky (§5.1)

Das 4.308 TSRs, 1.121 tiveram ao menos uma falha. Destas:

- **1.035 falhas de regressão** (bugs reais introduzidos por mudanças no código)
- **146 falhas flaky** (passam/falham sem mudança de código), distribuídas em 3 categorias:

| Categoria | Qtd | Descrição |
|---|---|---|
| **OD (Order-Dependent)** | 112 (77%) | 107 Victims (falham se executados após um polluter), 5 Brittles (passam só após state-setter) |
| **Concurrency** | 6 | Falham apenas sob `pytest-xdist` (múltiplos processos competindo por recurso) |
| **ND (Non-Deterministic)** | 28 | Comportamento não-determinístico de APIs (ex: geradores aleatórios) |

Testes flaky são **7× menos frequentes** que regressão mas falham **2.6× mais vezes por teste** (ciclo de vida mais longo). #10 execuções extras do Random expuseram +34 flaky tests.

### Resultados de Efetividade (§5.2)

`pytest-ranking` detecta falhas **mais rápido** que default e aleatório:

| Técnica | APFDc médio | vs. Default | vs. Random |
|---|---|---|---|
| **Default** (linha base) | 0.47 | — | — |
| **Random** (linha base) | 0.50 | — | — |
| QTF | 0.78 | +66% | +56% |
| RecentFail | 0.65 | +38% | +30% |
| SimChgPath | 0.66 | +40% | +32% |
| **Hybrid** (0-0.5-0.5) | **0.83** | **+77%** | **+66%** |

Overhead computacional **muito baixo**:
- Runtime médio: **0.1s** (0.03% da duração total da TSR)
- Cache: **6–538 KB** (média 5% do tamanho do log de CI)
- Duração da TSR varia apenas 1–10% entre ordens diferentes (média 4%)

### Citação

```bibtex
@inproceedings{cheng2025pytest,
  title={{pytest-ranking: A Regression Test Prioritization Tool for Python}},
  author={Cheng, Runxiang and Ke, Kaiyao and Marinov, Darko},
  booktitle={Companion Proceedings of the 33rd ACM International Conference
             on the Foundations of Software Engineering},
  year={2025},
}
```

---

## Deploy em CI/CD

### Setup Básico

Segundo o artigo (§3), o setup em GitHub Actions adiciona **apenas 14 linhas de YAML** ao arquivo de workflow. O plugin persiste dados no cache do pytest (`.pytest_cache/v/pytest_ranking_data/`). Em CI efêmero (ex: GitHub Actions), é necessário:

1. **Restore** antes do `pytest`: `actions/cache/restore@v4` apontando para `.pytest_cache/v/pytest_ranking_data`
2. **Save** após o `pytest`: `actions/cache/save@v4` apontando para o mesmo path

Para projetos com Tox, o `cachedir` fica dentro de `.tox/TOX_ENV_NAME/.pytest_cache/`.

### Exemplo Completo de Workflow (GitHub Actions)

```yaml
- name: Restore pytest-ranking cache
  id: restore-pytest-ranking-cache
  if: always()
  uses: actions/cache/restore@v4
  with:
    path: ${{ github.workspace }}/.pytest_cache/v/pytest_ranking_data
    key: pytest-ranking-cache-${{ runner.os }}-${{ matrix.python }}

- name: Install dependencies
  run: |
    pip install pytest-ranking
    pip install -r requirements.txt

- name: Run tests with pytest-ranking
  run: pytest --rank --rank-weight=0-0.5-0.5

- name: Save pytest-ranking cache
  id: save-pytest-ranking-cache
  if: always()
  uses: actions/cache/save@v4
  with:
    path: ${{ github.workspace }}/.pytest_cache/v/pytest_ranking_data
    key: pytest-ranking-cache-${{ runner.os }}-${{ matrix.python }}-${{ github.run_id }}
```

### Experimento de Reexecução no Mundo Real (§4.2)

Diferente de estudos anteriores que apenas **simulavam** ordens RTP em dados históricos, o artigo executou de fato as suites reordenadas no CI real. O procedimento foi:

1. **Fork** de cada projeto e setup do `pytest-ranking` no workflow do GitHub Actions
2. Para cada build histórico, obtém-se o **archive zip** do repositório no commit exato ([14])
3. Sobrescreve o fork com o conteúdo do archive, exceto pelos **arquivos de CI modificados**
4. Adiciona `uv.toml` com `exclude-newer` para instalar dependências compatíveis com a época do build
5. Faz **push** do código para o fork, disparando o GitHub Actions automaticamente
6. **Download** dos logs e artefatos (relatório JSON dos testes via `pytest-json-report`)
7. Para simular **overlap de builds**: se o build _i+1_ começou após o _i_ terminar, executa sequencialmente (usa cache atualizado); caso contrário, executa em paralelo (usa cache anterior)

### Ordens Executadas no Experimento

Para cada build, 6 workflows separados (para não haver interferência de cache):

| Workflow | Flag | Objetivo |
|---|---|---|
| **Default** | `pytest` (sem `--rank`) | Linha base — ordem padrão do pytest |
| **Random** | `--rank-weight=0-0-0` | Linha base — ordem aleatória |
| **QTF** | `--rank-weight=1-0-0` | Testes mais rápidos primeiro |
| **RecentFail** | `--rank-weight=0-1-0` | Falhas recentes primeiro |
| **SimChgPath** | `--rank-weight=0-0-1` | Similaridade com mudanças |
| **Hybrid** | `--rank-weight=0-0.5-0.5` | Combinação linear com pesos iguais |

Para o Random, foram feitas **10 execuções adicionais** por build com falha, usando o `run_id` como semente.

### Seleção de Builds para Reexecução

Dos 27.224 builds coletados, nem todos foram reexecutados. Para cada projeto:
- Selecionam-se **todos os builds com falha**
- Para cada build com falha, seleciona-se o **primeiro build bem-sucedido não-overlap anterior** (para criar o cache de dados correto)
- Continua até atingir o último build ou o **50º build**; depois continua até pelo menos **30 TSRs com falha** por projeto
- Total: **718 commits** reexecutados com sucesso → **4.308 TSRs** (6 ordens cada)

### Compatibilidade com Versões de Dependências

Como builds históricos podem exigir versões antigas de dependências, o experimento integrou o **UV** com a opção `--exclude-newer` configurada para a data de início de cada build, garantindo que apenas versões lançadas antes daquela data fossem instaladas.

---

## Referências

- Código: https://github.com/softwareTestingResearch/pytest-ranking
- PyPI: https://pypi.org/project/pytest-ranking
- Artigo: https://doi.org/10.1145/3696630.3728587
- Demo: https://youtu.be/SrnkgTs3uok
- Tese: https://hdl.handle.net/2142/129204

---

## Repositório de Artefatos (pytest-ranking-artifact)

O repositório **pytest-ranking-artifact** (https://github.com/softwareTestingResearch/pytest-ranking-artifact) contém scripts e dados utilizados nos experimentos de avaliação do plugin. Ele está dividido em duas pastas principais.

### project_selection_scripts — Curadoria de Projetos Candidatos

Scripts para selecionar projetos a partir do PyPI e filtrar candidatos viáveis para avaliação.

| Script | Finalidade |
|---|---|
| `get_project_list.py` | Obtém lista dos projetos mais baixados em 2023 via BigQuery público do PyPI (`bigquery-public-data.pypi.file_downloads`), filtra top 2500, coleta metadados (classificadores, versão, `requires_python`, `requires_dist`) via API JSON do PyPI, e gera `project_candidate.csv` |
| `get_project_stats_via_github.py` | Obtém estatísticas do GitHub para os projetos candidatos (estrelas, forks, etc.) |
| `get_project_commit_stats.py` | Coleta commits de 2024 para cada projeto candidato, incluindo HEAD commit e status |
| `get_commit_status_df.py` | Gera DataFrame com estatísticas de commits por projeto |
| `get_commit_status_via_github.py` | Consulta status de commits via API GitHub |
| `const.py` | Diretórios de metadados, commits e buffer |
| `token_pool.py` | Pool de tokens de autenticação GitHub para rate limiting |

**Processo de seleção:**
1. Consulta ao BigQuery público do PyPI para downloads em 2023
2. Filtra top 2500 projetos mais baixados
3. Para cada projeto, coleta metadados via API PyPI JSON
4. Filtra projetos que **declaram dependência do pytest** (`requires_dist` contém `"pytest "`)
5. Filtra projetos com **URL GitHub válida** e **versão Python definida**
6. Remove duplicatas de URL GitHub (mantém apenas um slug por repositório)

### rerun_test_build_scripts — Reexecução de Builds e Avaliação

Scripts para coletar builds históricos, reexecutá-los em CI com diferentes ordens de teste, baixar resultados e computar métricas.

| Script | Finalidade |
|---|---|
| `download_global_runs_dataset.py` | Cura lista de builds históricos do GitHub Actions CI a partir de `project_meta.json`; coleta metadados do build, metadados do commit e archive zip do repositório |
| `rerun_global_runs.py` | Reexecuta builds históricos em 6 ordens diferentes via GitHub Actions. Suporta CLI: `setup` (clona fork, backup CI files), `rerun` (checkout commit, modifica CI, push e dispara workflow), `download` (baixa logs e artefatos) |
| `rerun_random.py` | Reexecuta builds com ordem aleatória (10x por build, cada execução usa run_id como seed). Requer `regression_failed_runs.json` como entrada |
| `metrics.py` | Implementa as métricas de avaliação: classe `FaultDetectionMetric` com métodos `APFD()` e `APFDc()`, função `compute_metrics()`. Suporta dois mapeamentos falha-para-bug: `sameBug` (many-to-one — todas falhas contam como mesmo bug) e `uniqueBug` (one-to-one — cada falha conta como bug distinto) |
| `main.py` | Wrapper de linha de comando para `rerun_global_runs` |
| `local_const.py` | Constantes: URLs da API GitHub, nomes dos workflows, diretórios de dados, regex de status |
| `local_utils.py` | Utilitários: parsing de timestamps, extração de URL de artefato, etc. |
| `token_pool.py` | Pool de tokens GitHub para requisições autenticadas |
| `project_meta.json` | Metadados dos 14 projetos avaliados: `name`, `origin_slug`, `fork_slug`, `fork_branch`, `edited_ci_file_paths` |

### Ordens de Teste Avaliadas

Definidas em `local_const.py` com 6 workflows de CI diferentes:

| Workflow | Nome no Experimento | Descrição |
|---|---|---|
| `pytest_default_order` | **Default** | Ordem padrão do pytest (sem `--rank`) |
| `random_order` | **Random** | Ordem aleatória (`--rank-weight=0-0-0`) |
| `qtf_order` | **QTF** | Quickest-test-first: `--rank-weight=1-0-0` (padrão do plugin) |
| `recent_fail_order` | **RecentFail** | Falhas recentes primeiro: `--rank-weight=0-1-0` |
| `change_first_order` | **SimChgPath** | Similaridade com mudanças: `--rank-weight=0-0-1` |
| `mix_order` | **Hybrid** | Combinação linear: `--rank-weight=0-0.5-0.5` |

### eval_results — Análise dos Resultados

| Script/Arquivo | Finalidade |
|---|---|
| `parse_rerun_results.py` | Parseia artefatos baixados para CSVs de resultado por (projeto, commit, ordem) |
| `analyze_rerun_results.py` | Computa resultados da avaliação. Gera: `dataset_statistics.csv`, `APFDc_one2one.csv`, `APFDc_many2one.csv`, `failure_statistics.csv`, `overhead_statistics.csv` |
| `flaky_test_failures.csv` | Falhas identificadas como flaky (inspenção manual) |
| `real_test_failures.csv` | Falhas reais de regressão (inspeção manual) |
| `regression_failed_runs.json` | Build IDs que contêm falhas de regressão |

### Métricas de Avaliação (metrics.py)

**APFD (Average Percentage of Faults Detected):**
```
APFD = 1 - (sum(TFis) / (num_bugs * num_tests)) + (1 / (2 * num_tests))

onde TFis = posições (1-indexed) dos testes que falham
```

**APFDc (APFD com custo — duração dos testes):**
```
APFDc = sum(custos_TF) / (num_bugs * sum(todas_durações))

onde custo_TF(pos) = sum(duração[pos-1:]) - (duração[pos-1] / 2)
```

### Dados Disponíveis para Download

- **Dados brutos (~4 GB)**: Logs de CI e relatórios JSON de todas as ordens — https://drive.google.com/file/d/1osFBDosPCqmlkbkNGZ6dWA53lvhwkDM3
- **Dados brutos (~1 GB)**: Logs de CI das 10 execuções aleatórias — https://drive.google.com/file/d/1c-9SWRBmK3EILkXPQDViEPMk8VrJQInG
- **Dados processados (~500 MB)**: CSVs de resultados parseados — https://drive.google.com/file/d/1zLfE9WkHMtqpQoWPaWgHsUmW4wN0GngF
- **Arquivos de CI modificados**: `modified_ci_files_for_rerun.zip` e `modified_ci_files_for_rerun_random_order.zip`

### Processo de Reexecução (rerun_global_runs.py)

O script `ForkProject` implementa o pipeline completo:

1. **Setup**: Clona o fork do projeto, faz backup dos arquivos de CI originais
2. **Rerun**: Para cada build histórico:
   - Baixa o archive zip do repositório no commit exato
   - Substitui os arquivos de CI pelos modificados (com suporte a pytest-ranking + cache restore/save)
   - Adiciona `uv.toml` com `exclude-newer` para instalar dependências compatíveis com a época
   - Adiciona `pytest_ranking_seed.txt` com o run_id como seed para ordem aleatória
   - Faz push force para o fork, disparando o workflow do GitHub Actions
   - Executa builds em paralelo simulando overlap (respeitando a timeline real)
3. **Download**: Após conclusão, baixa logs e artefatos (relatório JSON dos testes via `pytest-json-report`)

### Arquivos de CI Modificados

Os arquivos `.zip` contêm workflows do GitHub Actions adaptados para cada projeto para:
- Instalar `pytest-ranking` como dependência
- Adicionar cache restore/save de `.pytest_cache/v/pytest_ranking_data`
- Executar pytest com a flag `--rank` e pesos específicos de cada ordem
- Fazer upload do relatório JSON como artefato do workflow

### Dependências (requirements.txt)

```
numpy
pandas
Requests
pre-commit
```
