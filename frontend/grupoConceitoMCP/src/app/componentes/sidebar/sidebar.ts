import { Component, ViewChild, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { iniciais } from '../../servicos/iniciais';
import { Sessao } from '../../servicos/sessao';
import { ConfiguracoesUsuario } from '../configuracoes-usuario/configuracoes-usuario';

const CHAVE_COLAPSADO = 'sidebar:colapsado';

@Component({
  selector: 'app-sidebar',
  imports: [RouterLink, RouterLinkActive, ConfiguracoesUsuario],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss'
})
export class Sidebar {
  protected readonly sessao = inject(Sessao);
  protected readonly iniciais = iniciais;
  private readonly router = inject(Router);

  @ViewChild(ConfiguracoesUsuario) private readonly configuracoes!: ConfiguracoesUsuario;

  protected readonly sidebarOpen = signal(false);
  protected readonly financeiroOpen = signal(false);
  protected readonly estoqueOpen = signal(false);
  protected readonly colapsado = signal(localStorage.getItem(CHAVE_COLAPSADO) === 'true');

  toggleSidebar(): void {
    this.sidebarOpen.update((value) => !value);
  }

  closeSidebar(): void {
    this.sidebarOpen.set(false);
  }

  /** Usado pelos links FORA dos grupos Financeiro/Estoque — navegar pra
   * outra área fecha os dois submenus, já que deixou de fazer sentido
   * continuar abertos. */
  navegarParaFora(): void {
    this.financeiroOpen.set(false);
    this.estoqueOpen.set(false);
    this.closeSidebar();
  }

  alternarColapsado(): void {
    const novoValor = !this.colapsado();
    this.colapsado.set(novoValor);
    this.financeiroOpen.set(false);
    this.estoqueOpen.set(false);
    localStorage.setItem(CHAVE_COLAPSADO, String(novoValor));
  }

  /** Só um dos dois grupos fica aberto por vez (accordion) — abrir um fecha
   * o outro, se estiver aberto. */
  toggleFinanceiro(): void {
    this.estoqueOpen.set(false);
    this.financeiroOpen.update((value) => !value);
  }

  toggleEstoque(): void {
    this.financeiroOpen.set(false);
    this.estoqueOpen.update((value) => !value);
  }

  abrirConfiguracoes(): void {
    this.configuracoes.abrir();
  }

  sair(): void {
    this.sessao.sair();
    this.router.navigateByUrl('/login');
  }
}
