import { Component, computed, inject } from '@angular/core';
import { EstoqueHome } from '../modulos/estoque/home/estoque-home';
import { Home } from '../home/home';
import { HomeSelecionada } from '../../servicos/home-selecionada';
import { Sessao } from '../../servicos/sessao';

/** Decide qual "home" de módulo mostrar na rota `/`, sem navegação nem
 * reload — só troca o componente renderizado:
 * - Desenvolvedor: usa o módulo escolhido em `SeletorHomeDev` (select ao
 *   lado do sino de auditoria).
 * - Todo mundo com o módulo Financeiro liberado (inclusive quem também tem
 *   Estoque): continua vendo a Home do Financeiro — comportamento igual ao
 *   de antes dessa página existir, ninguém perde a experiência atual.
 * - Quem só tem Estoque liberado: vê a Home do Estoque — esse é o caso novo
 *   que essa página resolve (antes, um usuário só-estoque caía na Home do
 *   Financeiro, que nem faz sentido pra ele). */
@Component({
  selector: 'app-home-roteador',
  imports: [EstoqueHome, Home],
  templateUrl: './home-roteador.html',
})
export class HomeRoteador {
  private readonly sessao = inject(Sessao);
  private readonly homeSelecionada = inject(HomeSelecionada);

  protected readonly moduloAtivo = computed(() => {
    if (this.sessao.ehDesenvolvedor()) {
      return this.homeSelecionada.modulo();
    }
    return this.sessao.modulos().includes('financeiro') ? 'financeiro' : 'estoque';
  });
}
