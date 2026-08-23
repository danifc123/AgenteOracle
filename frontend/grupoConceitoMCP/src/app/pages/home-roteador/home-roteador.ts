import { Component, computed, inject } from '@angular/core';
import { EstoqueHome } from '../modulos/estoque/home/estoque-home';
import { FinanceiroHome } from '../modulos/financeiro/home/financeiro-home';
import { RhHome } from '../modulos/rh/home/rh-home';
import { TiHome } from '../modulos/ti/home/ti-home';
import { HomeSelecionada } from '../../servicos/home-selecionada';
import { Sessao } from '../../servicos/sessao';

/** Ordem de prioridade quando o usuário tem mais de um módulo liberado ao
 * mesmo tempo (hoje só desenvolvedor) — Financeiro continua primeiro pra
 * não mudar a experiência de quem já usava o sistema antes dessa página
 * existir. Módulo sem home própria cai no primeiro da lista que ele tiver. */
const PRIORIDADE_MODULOS = ['financeiro', 'estoque', 'rh', 'ti'];

/** Decide qual "home" de módulo mostrar na rota `/`, sem navegação nem
 * reload — só troca o componente renderizado:
 * - Desenvolvedor: usa o módulo escolhido em `SeletorHomeDev` (select ao
 *   lado do sino de auditoria).
 * - Todo mundo: vê a home do módulo liberado de maior prioridade
 *   (`PRIORIDADE_MODULOS`) — antes só Financeiro/Estoque eram
 *   reconhecidos, então um usuário só-RH ou só-TI caía incorretamente na
 *   Home do Financeiro. */
@Component({
  selector: 'app-home-roteador',
  imports: [EstoqueHome, FinanceiroHome, RhHome, TiHome],
  templateUrl: './home-roteador.html',
})
export class HomeRoteador {
  private readonly sessao = inject(Sessao);
  private readonly homeSelecionada = inject(HomeSelecionada);

  protected readonly moduloAtivo = computed(() => {
    if (this.sessao.ehDesenvolvedor()) {
      return this.homeSelecionada.modulo();
    }
    const modulos = this.sessao.modulos();
    return PRIORIDADE_MODULOS.find((modulo) => modulos.includes(modulo)) ?? 'financeiro';
  });
}
