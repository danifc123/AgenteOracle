import { Component, ViewChild, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { AnaliseCurriculo } from '../../servicos/analise-curriculo';
import { iniciais } from '../../servicos/iniciais';
import { Sessao } from '../../servicos/sessao';
import { ConfiguracoesUsuario } from '../configuracoes-usuario/configuracoes-usuario';

const CHAVE_COLAPSADO = 'sidebar:colapsado';

@Component({
  selector: 'app-sidebar',
  imports: [RouterLink, RouterLinkActive, ConfiguracoesUsuario],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss',
})
export class Sidebar {
  protected readonly sessao = inject(Sessao);
  protected readonly analiseCurriculo = inject(AnaliseCurriculo);
  protected readonly iniciais = iniciais;
  private readonly router = inject(Router);

  @ViewChild(ConfiguracoesUsuario) private readonly configuracoes!: ConfiguracoesUsuario;

  protected readonly sidebarOpen = signal(false);
  protected readonly financeiroOpen = signal(false);
  protected readonly estoqueOpen = signal(false);
  protected readonly rhOpen = signal(false);
  protected readonly colapsado = signal(localStorage.getItem(CHAVE_COLAPSADO) === 'true');

  abrirConfiguracoes(): void {
    this.configuracoes.abrir();
  }

  alternarColapsado(): void {
    const novoValor = !this.colapsado();
    this.colapsado.set(novoValor);
    this.financeiroOpen.set(false);
    this.estoqueOpen.set(false);
    this.rhOpen.set(false);
    localStorage.setItem(CHAVE_COLAPSADO, String(novoValor));
  }

  closeSidebar(): void {
    this.sidebarOpen.set(false);
  }

  /** Usado pelos links FORA dos grupos Financeiro/Estoque/RH — navegar pra
   * outra área fecha os três submenus, já que deixou de fazer sentido
   * continuar abertos. */
  navegarParaFora(): void {
    this.financeiroOpen.set(false);
    this.estoqueOpen.set(false);
    this.rhOpen.set(false);
    this.closeSidebar();
  }

  sair(): void {
    this.sessao.sair();
    this.router.navigateByUrl('/login');
  }

  toggleEstoque(): void {
    this.financeiroOpen.set(false);
    this.rhOpen.set(false);
    this.estoqueOpen.update((value) => !value);
  }

  /** Só um dos três grupos fica aberto por vez (accordion) — abrir um fecha
   * os outros, se estiverem abertos. */
  toggleFinanceiro(): void {
    this.estoqueOpen.set(false);
    this.rhOpen.set(false);
    this.financeiroOpen.update((value) => !value);
  }

  /** Clicar no grupo "RH" também marca toda notificação/erro pendente como
   * visto — a bolinha laranja some assim que o usuário entra no módulo, em
   * vez de exigir que ele veja/dispense cada toast um por um. */
  toggleRh(): void {
    this.financeiroOpen.set(false);
    this.estoqueOpen.set(false);
    this.rhOpen.update((value) => !value);
    this.analiseCurriculo.marcarTudoComoVisto();
  }

  toggleSidebar(): void {
    this.sidebarOpen.update((value) => !value);
  }
}
