import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { Sessao } from '../../servicos/sessao';

@Component({
  selector: 'app-sidebar',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss'
})
export class Sidebar {
  private readonly sessao = inject(Sessao);
  private readonly router = inject(Router);

  protected readonly sidebarOpen = signal(false);
  protected readonly financeiroOpen = signal(false);

  toggleSidebar(): void {
    this.sidebarOpen.update((value) => !value);
  }

  closeSidebar(): void {
    this.sidebarOpen.set(false);
  }

  toggleFinanceiro(): void {
    this.financeiroOpen.update((value) => !value);
  }

  sair(): void {
    this.sessao.sair();
    this.router.navigateByUrl('/login');
  }
}
