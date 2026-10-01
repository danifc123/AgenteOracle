import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { ConteudoChamado } from '../../../../componentes/conteudo-chamado/conteudo-chamado';
import { ConfiguracoesChamados } from '../../../../componentes/configuracoes-chamados/configuracoes-chamados';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { SaudeArea, SaudeRoster } from '../../../../componentes/saude-roster/saude-roster';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';
import { Selo } from '../../../../componentes/selo/selo';
import { SoDev } from '../../../../diretivas/so-dev/so-dev';
import { ConfiguracoesTi } from '../../../../servicos/configuracoes-ti/configuracoes-ti';
import { Sessao } from '../../../../servicos/sessao/sessao';
import { IndicadoresTecnico } from './indicadores-tecnico/indicadores-tecnico';

export type StatusChamado = 'novo' | 'aguardando_usuario' | 'fila_atendimento';

// Mesmos 3 valores/rótulos de `server/ti/chamados.py::_ROTULOS_AREA` —
// duplicado de propósito (é uma constante de exibição, não vale acoplar
// front/back só por isso). Usado no botão/tooltip do filtro por área.
const ROTULOS_AREA: Record<'infra' | 'sistemas' | 'processos', string> = {
  infra: 'Infraestrutura',
  sistemas: 'Sistemas',
  processos: 'Processos',
};

export interface Chamado {
  id: number;
  titulo: string;
  descricao: string;
  categoria: string;
  status: StatusChamado;
  solicitante: string;
  avaliacao_mensagem: string | null;
  criado_em: string;
  area: 'infra' | 'sistemas' | 'processos';
  tecnico_atribuido: string | null;
  // `true` = chamado que um técnico de verdade já está tratando fora do
  // fluxo da IA (ver `tools/ti/glpi.py::chamado_e_alheio`) — "Minha
  // área" esconde esse chamado (mostrar ele junto com os que ainda
  // dependem da nossa triagem só confunde, e ele não "tende a cair" pra
  // ninguém — já foi pego); "Meus chamados"/"Todo o departamento"
  // mostram de propósito.
  gerenciado_fora_do_sistema: boolean;
}

interface TecnicoNome {
  identificador: string;
  nome: string;
  // Login do AgenteOracle (não do GLPI) — usado só pra achar "qual técnico
  // sou eu" nos filtros "Minha área"/"Meus chamados" (compara com
  // `sessao.usuario()`).
  usuario: string;
  // Área do técnico logado — o filtro "Minha área" usa ISSO, não
  // `tecnico_atribuido` (ver comentário de `minhaArea` mais abaixo).
  area: 'infra' | 'sistemas' | 'processos';
}

// Valor selecionado no `app-select-busca` do cabeçalho da lista — `null`/
// ausente do select (`aoTrocarFiltro`) sempre cai em `'departamento'`:
// só 3 opções, sem um "Todos" à parte (tirado de propósito — "Todos" e
// "Todo o departamento" liam parecido demais e um deles escondia
// chamado sem avisar; "Todo o departamento" já é o estado neutro,
// mostra tudo que está novo ou aguardando resposta no GLPI, igual lá).
type FiltroChamados = 'area' | 'meus' | 'departamento';

/** MÓDULO TI — TELA "AUDITORIA DE CHAMADOS" (2026-08)
 *
 * Item "Service Desk IA" da planilha de demandas — integração real com o
 * GLPI (`tools/ti/glpi.py::ClienteGLPIReal`), sem cliente mock. Um poller
 * em background no próprio servidor (`server/ti/chamados.py::
 * iniciar_poller_verificar_chamados`) roda sozinho a cada poucos minutos,
 * em duas pernas: chamado `novo` é sempre avaliado; chamado
 * `aguardando_usuario` só é reavaliado quando o poller detecta uma
 * resposta nova do solicitante (não gasta IA à toa num chamado parado).
 * Se a IA insistir que falta informação numa 2ª avaliação seguida, o
 * chamado é escalado pra um técnico humano (`tecnicoEscalado()` mostra
 * isso na tela — "Aguardando resposta" vira "Com {técnico}").
 *
 * A engrenagem no cabeçalho (só desenvolvedor) abre as configurações da Auditoria (`ConfiguracoesChamados`).
 *
 * Sem botão de "reportar ao usuário" de propósito: o Followup que a IA
 * posta ao marcar `aguardando_usuario` já dispara a notificação nativa
 * do GLPI pro solicitante (mecanismo padrão dele pra mensagem em
 * chamado) — nenhum aviso extra é necessário da nossa parte.
 *
 * Sem botão de "Verificar" individual de propósito (removido 2026-09-28):
 * a régua de quando escalar pra um técnico (`_LIMITE_RODADAS_ESCLARECIMENTO`
 * rodadas REAIS do solicitante, não reavaliações manuais — ver
 * `server/ti/chamados.py::processar_chamado_novo`) nunca é alcançada só de
 * clicar o botão repetidas vezes, então ele só empilhava Followups
 * repetidos no GLPI de verdade sem nunca escalar — confundia mais do que
 * ajudava. A tela em si só carrega a lista uma vez, ao abrir — não se
 * atualiza sozinha enquanto o poller processa em background; recarregar
 * a página mostra o estado mais recente. */
@Component({
  selector: 'app-chamados-ti',
  imports: [
    Botao,
    ConfiguracoesChamados,
    ConteudoChamado,
    DatePipe,
    Dialog,
    EstadoVazio,
    IndicadoresTecnico,
    ModuloHeader,
    SaudeRoster,
    SelectBusca,
    Selo,
    SoDev,
  ],
  templateUrl: './chamados.html',
  styleUrl: './chamados.scss',
})
export class ChamadosTi {
  private readonly http = inject(HttpClient);
  private readonly configuracoesTi = inject(ConfiguracoesTi);
  protected readonly sessao = inject(Sessao);
  private readonly ITENS_POR_PAGINA = 10;

  // Painel de diagnóstico só-desenvolvedor (`/api/ti/tecnicos/saude`,
  // restrito a `exigir_desenvolvedor` no backend) — mostra técnico
  // cadastrado por área, pra pegar área com zero técnicos (causa real de um
  // 500 em `escolher_tecnico`, `tools/ti/tecnicos.py`) antes de alguém
  // tropeçar nisso usando a tela de verdade.
  protected readonly saudeAreas = signal<SaudeArea[]>([]);

  protected readonly chamados = signal<Chamado[]>([]);
  protected readonly carregando = signal(true);
  protected readonly chamadoAberto = signal<Chamado | null>(null);
  protected readonly configuracoesAbertas = signal(false);
  // Avisa de relance (só desenvolvedor) que há amostragem ativa.
  protected readonly amostragemAtiva = computed(
    () => this.configuracoesTi.percentualAmostragemChamados() < 100,
  );
  protected readonly percentualFormatado = computed(() =>
    this.configuracoesTi
      .percentualAmostragemChamados()
      .toLocaleString('pt-BR', { maximumFractionDigits: 3 }),
  );
  // Nome pro badge "Com {técnico}" — vem do roster de verdade
  // (`/api/ti/tecnicos`, backend por `tools/ti/tecnicos.py`), não mais
  // fixo aqui — um técnico novo cadastrado aparece certo sem precisar
  // editar o frontend.
  private readonly nomesTecnicos = signal<Record<string, string>>({});
  // Área do técnico ligado à conta logada — `null` quando a conta não tem
  // técnico do GLPI vinculado (ex: `ti_admin` sem atendimento). Alimenta o
  // filtro por área. NÃO usa `tecnico_atribuido`: esse campo só é
  // preenchido no instante em que o chamado vira `fila_atendimento` — e
  // `_precisa_atencao` (backend) já exclui esse status desta tela, então
  // filtrar por atribuição literal nunca mostraria nada; a área é o que
  // de fato indica "isso tende a cair pra mim".
  protected readonly minhaArea = signal<'infra' | 'sistemas' | 'processos' | null>(null);
  protected readonly rotuloMinhaArea = computed(() => {
    const area = this.minhaArea();
    return area ? ROTULOS_AREA[area] : null;
  });
  // Id do técnico GLPI ligado à conta logada — diferente de `minhaArea`,
  // ESTE alimenta "Meus chamados": só faz sentido pra chamado que JÁ foi
  // atribuído a um técnico. O backend (`chamados_route`) sempre busca com
  // `incluir_atribuidos=True` — a resposta já vem com todo chamado
  // atribuído, de qualquer técnico, marcado (`gerenciado_fora_do_sistema`)
  // — é este filtro, no front, que decide o que mostrar em cada opção.
  // `null` = sem técnico GLPI vinculado, mesma regra de `minhaArea`.
  protected readonly meuIdentificador = signal<string | null>(null);
  protected readonly filtroChamados = signal<FiltroChamados>('departamento');

  protected readonly opcoesFiltro = computed<OpcaoSelectBusca[]>(() => {
    const opcoes: OpcaoSelectBusca[] = [];
    const rotuloArea = this.rotuloMinhaArea();
    if (rotuloArea) {
      opcoes.push({ valor: 'area', rotulo: 'Minha área: ' + rotuloArea });
    }
    if (this.meuIdentificador()) {
      opcoes.push({ valor: 'meus', rotulo: 'Meus chamados' });
    }
    opcoes.push({ valor: 'departamento', rotulo: 'Todo o departamento' });
    return opcoes;
  });

  protected readonly chamadosFiltrados = computed(() => {
    const filtro = this.filtroChamados();
    if (filtro === 'meus') {
      const identificador = this.meuIdentificador();
      return identificador
        ? this.chamados().filter((chamado) => chamado.tecnico_atribuido === identificador)
        : this.chamados();
    }
    if (filtro === 'area') {
      const area = this.minhaArea();
      return area
        ? this.chamados().filter(
            (chamado) => !chamado.gerenciado_fora_do_sistema && chamado.area === area,
          )
        : this.chamados();
    }
    // 'departamento' (padrão) — tudo, de qualquer técnico, sem exceção.
    return this.chamados();
  });

  protected readonly paginaAtual = signal(1);
  protected readonly totalPaginas = computed(() =>
    Math.max(1, Math.ceil(this.chamadosFiltrados().length / this.ITENS_POR_PAGINA)),
  );
  protected readonly chamadosDaPagina = computed(() => {
    const inicio = (this.paginaAtual() - 1) * this.ITENS_POR_PAGINA;
    return this.chamadosFiltrados().slice(inicio, inicio + this.ITENS_POR_PAGINA);
  });

  constructor() {
    this.carregarChamados();
    this.carregarTecnicos();
    if (this.sessao.ehDesenvolvedor()) {
      // As configurações só aparecem (e só são editáveis) pra desenvolvedor.
      this.configuracoesTi.carregar();
      this.carregarSaudeAreas();
    }
  }

  private carregarChamados(): void {
    this.carregando.set(true);
    this.http.get<Chamado[]>(`${MCP_API_BASE_URL}/api/ti/chamados`).subscribe({
      next: (chamados) => {
        this.chamados.set(chamados);
        this.paginaAtual.set(1);
        this.carregando.set(false);
      },
      error: () => this.carregando.set(false),
    });
  }

  private carregarSaudeAreas(): void {
    this.http.get<SaudeArea[]>(`${MCP_API_BASE_URL}/api/ti/tecnicos/saude`).subscribe({
      next: (areas) => this.saudeAreas.set(areas),
      error: () => this.saudeAreas.set([]),
    });
  }

  private carregarTecnicos(): void {
    this.http.get<TecnicoNome[]>(`${MCP_API_BASE_URL}/api/ti/tecnicos`).subscribe({
      next: (tecnicos) => {
        this.nomesTecnicos.set(
          Object.fromEntries(tecnicos.map((tecnico) => [tecnico.identificador, tecnico.nome])),
        );
        const meuTecnico = tecnicos.find((tecnico) => tecnico.usuario === this.sessao.usuario());
        this.minhaArea.set(meuTecnico?.area ?? null);
        this.meuIdentificador.set(meuTecnico?.identificador ?? null);
      },
      error: () => {
        this.nomesTecnicos.set({});
        this.minhaArea.set(null);
        this.meuIdentificador.set(null);
      },
    });
  }

  protected abrirDetalhe(chamado: Chamado): void {
    this.chamadoAberto.set(chamado);
  }

  protected aoTrocarFiltro(valor: string | null): void {
    this.filtroChamados.set((valor as FiltroChamados | null) ?? 'departamento');
    this.paginaAtual.set(1);
  }

  protected fecharDetalhe(): void {
    this.chamadoAberto.set(null);
  }

  protected paginaAnterior(): void {
    this.paginaAtual.update((atual) => Math.max(1, atual - 1));
  }

  protected proximaPagina(): void {
    this.paginaAtual.update((atual) => Math.min(this.totalPaginas(), atual + 1));
  }

  // `null` = ainda só com a IA (aguardando resposta do solicitante); um
  // nome = já escalado pra esse técnico.
  protected tecnicoEscalado(chamado: Chamado): string | null {
    return chamado.tecnico_atribuido
      ? (this.nomesTecnicos()[chamado.tecnico_atribuido] ?? null)
      : null;
  }
}
