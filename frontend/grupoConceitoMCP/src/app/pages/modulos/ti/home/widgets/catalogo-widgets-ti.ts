// Ids precisam ficar em sincronia com `_CATALOGO` em
// `server/ti/dashboard.py` — mesmo tipo de duplicação de string entre
// back/front já aceito no projeto (ex: módulos conhecidos).
export type IdWidgetTi =
  | 'chamados_total'
  | 'chamados_por_status'
  | 'ia_tokens_hoje'
  | 'ia_chamados_avaliados'
  | 'ia_chamados_escalados'
  | 'ia_categoria_nao_corrigida'
  | 'seguranca_achados_ativos';

export type TamanhoWidgetTi = 'pequeno' | 'grande';

export interface DefinicaoWidgetTi {
  id: IdWidgetTi;
  titulo: string;
  /** `true` = só aparece no catálogo pra quem `sessao.ehDesenvolvedor()`. */
  disponibilidadeDev: boolean;
  /** Tamanho usado quando o indicador é adicionado, ou quando o tamanho
   * salvo veio inválido — o usuário pode trocar depois (ver `ti-home.ts::alternarTamanho`). */
  tamanhoPadrao: TamanhoWidgetTi;
}

/** Um item do layout salvo — `id` mais o tamanho ESCOLHIDO (não
 * necessariamente o `tamanhoPadrao` do catálogo). */
export interface ItemLayoutTi {
  id: IdWidgetTi;
  tamanho: TamanhoWidgetTi;
}

export const CATALOGO_WIDGETS_TI: DefinicaoWidgetTi[] = [
  { id: 'chamados_total', titulo: 'Chamados em aberto', disponibilidadeDev: false, tamanhoPadrao: 'pequeno' },
  {
    id: 'chamados_por_status',
    titulo: 'Chamados por status',
    disponibilidadeDev: false,
    tamanhoPadrao: 'grande',
  },
  { id: 'ia_tokens_hoje', titulo: 'Tokens hoje', disponibilidadeDev: true, tamanhoPadrao: 'pequeno' },
  {
    id: 'ia_chamados_avaliados',
    titulo: 'Chamados avaliados pela IA (30d)',
    disponibilidadeDev: true,
    tamanhoPadrao: 'pequeno',
  },
  {
    id: 'ia_chamados_escalados',
    titulo: 'Escalados pra humano (30d)',
    disponibilidadeDev: true,
    tamanhoPadrao: 'pequeno',
  },
  {
    id: 'ia_categoria_nao_corrigida',
    titulo: 'Categoria não corrigida automaticamente (30d)',
    disponibilidadeDev: true,
    tamanhoPadrao: 'pequeno',
  },
  {
    id: 'seguranca_achados_ativos',
    titulo: 'Achados de segurança ativos',
    disponibilidadeDev: false,
    tamanhoPadrao: 'pequeno',
  },
];

export function idWidgetTiValido(id: string): id is IdWidgetTi {
  return CATALOGO_WIDGETS_TI.some((definicao) => definicao.id === id);
}

export function definicaoWidgetTi(id: IdWidgetTi): DefinicaoWidgetTi {
  // `id` só chega tipado como `IdWidgetTi` a partir de `idWidgetTiValido`
  // (ver `ti-home.ts::widgetsVisiveis`) — sempre existe no catálogo.
  return CATALOGO_WIDGETS_TI.find((definicao) => definicao.id === id)!;
}
