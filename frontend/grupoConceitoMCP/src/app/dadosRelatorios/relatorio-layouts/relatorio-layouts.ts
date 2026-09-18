/** Espelha o JSON devolvido por /api/financeiro/relatorio/layouts
 * (server/financeiro/layouts.py) — layouts salvos da tela "Criar Relatório":
 * presets de colunas selecionadas, filtros preenchidos e filiais escolhidas. */
export interface LayoutRelatorio {
  id: number;
  nome: string;
  colunas_selecionadas: Record<string, string[]>;
  valores_filtros: Record<string, string>;
  filiais_selecionadas: string[];
  criado_em: string;
  atualizado_em: string;
}
