import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { CartaoKpi } from '../../../../componentes/cartao-kpi/cartao-kpi';
import { SoDev } from '../../../../diretivas/so-dev/so-dev';
import { FatiaRosca, GraficoRosca } from '../../../../componentes/grafico-rosca/grafico-rosca';
import { AtalhoModulo, HomeModulo } from '../../../../componentes/home-modulo/home-modulo';
import { Selo } from '../../../../componentes/selo/selo';
import { Sessao } from '../../../../servicos/sessao/sessao';
import { UsoIa } from '../../../../servicos/uso-ia/uso-ia';

const ATALHOS: AtalhoModulo[] = [
  {
    titulo: 'Segurança de TI',
    texto:
      'A IA analisa padrão de login e volume de acesso a dado recente e aponta possível tentativa de invasão ou acesso suspeito.',
    rota: '/ti/seguranca',
    iconeSvg: `<path d="M12 3l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3Z" stroke-linecap="round" stroke-linejoin="round" /><path d="M12 8v5M12 16.5h.01" stroke-linecap="round" />`,
  },
  {
    titulo: 'Auditoria de Chamados',
    texto:
      'A IA audita cada chamado novo do GLPI e só libera pra fila de atendimento quando tem informação suficiente.',
    rota: '/ti/chamados',
    iconeSvg: `<path d="M4 5h16v11H8l-4 4V5Z" stroke-linecap="round" stroke-linejoin="round" /><path d="M8 10h8M8 13h5" stroke-linecap="round" />`,
  },
  {
    titulo: 'Central de suporte',
    texto: 'Encontrou um bug ou está com dificuldade? Abra um chamado no GLPI.',
    href: 'https://suporte.grupoconceito.com/front/central.php',
    iconeSvg: `<circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7v.3" stroke-linecap="round" stroke-linejoin="round" /><circle cx="12" cy="17" r="0.15" fill="currentColor" stroke-width="2.4" />`,
  },
];

const ROTULOS_STATUS: Record<string, string> = {
  novo: 'Novo',
  aguardando_usuario: 'Aguardando usuário',
  fila_atendimento: 'Fila de atendimento',
};

const CORES_STATUS: Record<string, string> = {
  novo: '#e8871e',
  aguardando_usuario: '#b5620a',
  fila_atendimento: '#2f9e58',
};

interface ChamadoResumo {
  status: string;
}

/** Home do time de TI — mostrada em `/` pra quem só tem o módulo TI
 * liberado, e pra desenvolvedor quando troca pro TI no seletor do layout.
 * Vira um "lobby" de verdade (2026-09): mantém o hero + atalhos de sempre
 * (`app-home-modulo`, casca compartilhada com RH/Financeiro) e ganha duas
 * seções novas embaixo:
 *
 * - Chamados em aberto (todo o time de TI) — reaproveita a MESMA chamada
 *   que a tela de Auditoria de Chamados já faz (`GET /api/ti/chamados`),
 *   só conta por status aqui; nenhum endpoint novo.
 * - Consumo de IA (`*appSoDev`) — token é custo de IA, já decidido nesta
 *   sessão como "só desenvolvedor vê" (a página Tokens inteira é dev-only,
 *   a API devolve 403 pra quem não é). Por isso a chamada a `UsoIa` só
 *   acontece se `sessao.ehDesenvolvedor()` — não é só esconder a seção na
 *   tela, é não disparar a chamada (que daria 403) pra quem não deveria
 *   nem saber que essa informação existe. */
@Component({
  selector: 'app-ti-home',
  imports: [CartaoKpi, GraficoRosca, HomeModulo, RouterLink, Selo, SoDev],
  templateUrl: './ti-home.html',
  styleUrl: './ti-home.scss',
})
export class TiHome {
  private readonly http = inject(HttpClient);
  protected readonly sessao = inject(Sessao);
  protected readonly usoIa = inject(UsoIa);

  protected readonly atalhos = ATALHOS;

  protected readonly chamados = signal<ChamadoResumo[]>([]);

  protected readonly totalChamadosAbertos = computed(() => this.chamados().length);

  protected readonly fatiasChamadosPorStatus = computed<FatiaRosca[]>(() => {
    const porStatus = new Map<string, number>();
    for (const chamado of this.chamados()) {
      porStatus.set(chamado.status, (porStatus.get(chamado.status) ?? 0) + 1);
    }
    return Array.from(porStatus.entries()).map(([status, quantidade]) => ({
      nome: ROTULOS_STATUS[status] ?? status,
      valor: quantidade,
      cor: CORES_STATUS[status] ?? '#5b6b62',
    }));
  });

  protected readonly tokensHojeTotal = computed(() =>
    Object.values(this.usoIa.tokensHojePorDominio()).reduce((total, valor) => total + valor, 0),
  );

  constructor() {
    this.http.get<ChamadoResumo[]>(`${MCP_API_BASE_URL}/api/ti/chamados`).subscribe({
      next: (chamados) => this.chamados.set(chamados),
    });
    if (this.sessao.ehDesenvolvedor()) {
      this.usoIa.carregar();
    }
  }
}
