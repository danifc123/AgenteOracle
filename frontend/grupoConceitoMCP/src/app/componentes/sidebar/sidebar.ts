import { Component, ViewChild, inject, signal } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { AnaliseCurriculo } from '../../servicos/analise-curriculo';
import { iniciais } from '../../servicos/iniciais';
import { Sessao } from '../../servicos/sessao';
import { ConfiguracoesUsuario } from '../configuracoes-usuario/configuracoes-usuario';
import { GRUPOS_MENU } from './itens-menu';

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
  private readonly sanitizer = inject(DomSanitizer);

  @ViewChild(ConfiguracoesUsuario) private readonly configuracoes!: ConfiguracoesUsuario;

  protected readonly grupos = GRUPOS_MENU;
  protected readonly sidebarOpen = signal(false);
  protected readonly grupoAberto = signal<string | null>(null);
  protected readonly colapsado = signal(localStorage.getItem(CHAVE_COLAPSADO) === 'true');

  abrirConfiguracoes(): void {
    this.configuracoes.abrir();
  }

  alternarColapsado(): void {
    const novoValor = !this.colapsado();
    this.colapsado.set(novoValor);
    this.grupoAberto.set(null);
    localStorage.setItem(CHAVE_COLAPSADO, String(novoValor));
  }

  closeSidebar(): void {
    this.sidebarOpen.set(false);
  }

  protected iconeSeguro(svg: string): SafeHtml {
    return this.sanitizer.bypassSecurityTrustHtml(svg);
  }

  /** Usado pelos links FORA dos grupos com submenu — navegar pra outra área
   * fecha o grupo aberto, já que deixou de fazer sentido continuar aberto. */
  navegarParaFora(): void {
    this.grupoAberto.set(null);
    this.closeSidebar();
  }

  sair(): void {
    this.sessao.sair();
    this.router.navigateByUrl('/login');
  }

  /** Só um grupo fica aberto por vez (accordion). Clicar no grupo "RH"
   * também marca toda notificação/erro pendente como visto — a bolinha
   * laranja some assim que o usuário entra no módulo, em vez de exigir que
   * ele veja/dispense cada toast um por um. */
  protected toggleGrupo(chave: string): void {
    this.grupoAberto.update((atual) => (atual === chave ? null : chave));
    if (chave === 'rh') {
      this.analiseCurriculo.marcarTudoComoVisto();
    }
  }

  toggleSidebar(): void {
    this.sidebarOpen.update((value) => !value);
  }
}
