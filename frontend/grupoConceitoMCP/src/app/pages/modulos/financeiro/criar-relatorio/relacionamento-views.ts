import { ViewFinanceira } from '../../../../dadosRelatorios/views-financeiras';

/** Grafo não-direcionado das views a partir dos relacionamentos declarados
 * (mesma ideia do `_grafo_relacionamentos` do backend, em
 * `relatorio_customizado_sql.py`) — usado só pra decidir quais tabelas
 * ficam bloqueadas na lista da tela; o backend continua sendo a fonte de
 * verdade que valida o join de fato na hora de gerar o relatório. */
export function construirGrafoRelacionamentos(views: ViewFinanceira[]): Map<string, Set<string>> {
  const grafo = new Map<string, Set<string>>();
  for (const view of views) {
    grafo.set(view.nome, grafo.get(view.nome) ?? new Set());
    for (const rel of view.relacionamentos) {
      if (!grafo.has(rel.viewDestino)) {
        grafo.set(rel.viewDestino, new Set());
      }
      grafo.get(view.nome)!.add(rel.viewDestino);
      grafo.get(rel.viewDestino)!.add(view.nome);
    }
  }
  return grafo;
}

/** Nomes das tabelas alcançáveis a partir de `selecionadas` (BFS), direto ou
 * por relacionamento indireto — `null` quando `selecionadas` está vazio, já
 * que nesse caso qualquer tabela pode ser a primeira da seleção. */
export function tabelasAlcancaveis(
  grafo: Map<string, Set<string>>,
  selecionadas: string[],
): Set<string> | null {
  if (!selecionadas.length) {
    return null;
  }

  const visitados = new Set(selecionadas);
  const fila = [...selecionadas];

  while (fila.length) {
    const atual = fila.shift()!;
    for (const vizinho of grafo.get(atual) ?? []) {
      if (!visitados.has(vizinho)) {
        visitados.add(vizinho);
        fila.push(vizinho);
      }
    }
  }

  return visitados;
}
