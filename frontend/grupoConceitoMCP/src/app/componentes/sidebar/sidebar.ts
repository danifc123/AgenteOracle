import { Component, ViewChild, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
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
  private readonly router = inject(Router);

  @ViewChild(ConfiguracoesUsuario) private readonly configuracoes!: ConfiguracoesUsuario;

  protected readonly sidebarOpen = signal(false);
  protected readonly financeiroOpen = signal(false);
  protected readonly colapsado = signal(localStorage.getItem(CHAVE_COLAPSADO) === 'true');

  toggleSidebar(): void {
    this.sidebarOpen.update((value) => !value);
  }

  closeSidebar(): void {
    this.sidebarOpen.set(false);
  }

  alternarColapsado(): void {
    const novoValor = !this.colapsado();
    this.colapsado.set(novoValor);
    this.financeiroOpen.set(false);
    localStorage.setItem(CHAVE_COLAPSADO, String(novoValor));
  }

  toggleFinanceiro(): void {
    if (this.colapsado()) {
      this.router.navigateByUrl('/financeiro/especifico-grupo-conceito');
      return;
    }
    this.financeiroOpen.update((value) => !value);
  }

  abrirConfiguracoes(): void {
    this.configuracoes.abrir();
  }

  sair(): void {
    this.sessao.sair();
    this.router.navigateByUrl('/login');
  }
}
