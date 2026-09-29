import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../../app-config';
import { CartaoKpi } from '../../../../../componentes/cartao-kpi/cartao-kpi';

interface RespostaMeusIndicadores {
  meus_chamados: number | null;
  media_chamados_equipe: number;
  meu_tempo_gasto_horas: number | null;
  media_tempo_gasto_equipe_horas: number;
}

const URL_MEUS_INDICADORES = `${MCP_API_BASE_URL}/api/ti/chamados/meus-indicadores`;

/** Área de indicadores da Auditoria de Chamados — autossuficiente (busca
 * o próprio dado, sem @Input), mesmo padrão dos widgets de
 * `pages/modulos/ti/home/widgets/`. Fica só nesta tela (não é widget de
 * Home): mostra, em cards bem visíveis (`app-cartao-kpi`, mesmo
 * componente de Financeiro/Estoque), quantos chamados o técnico logado
 * pegou nos últimos 30 dias e quanto tempo registrou neles, comparado
 * com a média entre todos os técnicos de TI — pra ele saber se está indo
 * bem sem abrir o GLPI.
 *
 * `meusChamados() === null` (usuário sem técnico vinculado, ex:
 * `desenvolvedor` sem `tecnico_glpi_id`) não renderiza nada — ver
 * `indicadores-tecnico.html`. Tempo gasto aparecendo 0h é esperado no
 * ambiente de homologação (ninguém registra `actiontime` lá) — não é bug
 * do componente, é o dado real de lá. */
@Component({
  selector: 'app-indicadores-tecnico',
  imports: [CartaoKpi],
  templateUrl: './indicadores-tecnico.html',
  styleUrl: './indicadores-tecnico.scss',
})
export class IndicadoresTecnico {
  private readonly http = inject(HttpClient);

  protected readonly meusChamados = signal<number | null>(null);
  protected readonly mediaChamadosEquipe = signal<number | null>(null);
  protected readonly meuTempoGastoHoras = signal<number | null>(null);
  protected readonly mediaTempoGastoEquipeHoras = signal<number | null>(null);

  protected readonly abaixoDaMediaChamados = computed(() => {
    const meus = this.meusChamados();
    const media = this.mediaChamadosEquipe();
    return meus !== null && media !== null && meus < media;
  });

  protected readonly abaixoDaMediaTempo = computed(() => {
    const meu = this.meuTempoGastoHoras();
    const media = this.mediaTempoGastoEquipeHoras();
    return meu !== null && media !== null && meu < media;
  });

  constructor() {
    this.http.get<RespostaMeusIndicadores>(URL_MEUS_INDICADORES).subscribe({
      next: (resposta) => {
        this.meusChamados.set(resposta.meus_chamados);
        this.mediaChamadosEquipe.set(resposta.media_chamados_equipe);
        this.meuTempoGastoHoras.set(resposta.meu_tempo_gasto_horas);
        this.mediaTempoGastoEquipeHoras.set(resposta.media_tempo_gasto_equipe_horas);
      },
    });
  }
}
