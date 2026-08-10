# Resultados do Benchmark de Indexação (B12)

Execução em 2026-08-10, máquina local do desenvolvedor.
Comando: `python3 benchmarks/benchmark_index.py --files 10000`

## Números reais (10.000 arquivos)

| Métrica | Valor |
|---------|-------|
| Arquivos sintéticos | 10.000 |
| Tempo de indexação | **47,94 s** |
| Pico de memória (tracemalloc) | **5,5 MB** |
| Nós no grafo | **90.000** |
| Arestas no grafo | **80.000** |
| Arquivos indexados | 10.000 |
| Tamanho do banco SQLite | **74,0 MB** |

## Notas de interpretação

- O repositório sintético é fixo (sem aleatoriedade): 4 funções por arquivo,
  com chamadas reais entre elas — os números são comparáveis entre execuções.
- **Pico de memória**: `tracemalloc` rastreia apenas alocações Python; o
  consumo real do processo (árvore tree-sitter + SQLite) é maior que 5,5 MB.
  Considere o valor um piso, não o pico real.
- **Tempo**: inclui a geração do repositório sintético? Não — apenas o
  `index_repository()` (scan, parse e persistência). A geração fica fora da
  medição.
- **Node count**: 90.000 = 10.000 arquivos × (1 nó file + 4 funções +
  4 chamadas + 1 import `from __future__`... na prática: 1 file + 4 function
  + 4 call por arquivo, mais o nó do módulo).
- Benchmark **não roda no CI** — é script standalone; `make check` não o
  referencia. Rodar sob demanda: `python3 benchmarks/benchmark_index.py`.
