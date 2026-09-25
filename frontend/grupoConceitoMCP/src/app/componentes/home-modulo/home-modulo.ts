import { Component, inject, input } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';
import { Sessao } from '../../servicos/sessao/sessao';

export interface AtalhoModulo {
  titulo: string;
  texto: string;
  /** Conteúdo interno do `<svg>` (paths/rects/circles), como HTML puro —
   * confiável porque vem só das constantes estáticas de cada home, nunca
   * de dado externo. */
  iconeSvg: string;
  /** Um dos dois deve ser informado: `rota` pra navegação interna
   * (`routerLink`), `href` pra link externo (abre em nova aba). */
  rota?: string;
  href?: string;
  /** Só o Financeiro usa — atalho visível apenas pra quem tem papel admin. */
  somenteAdmin?: boolean;
}

/** Casca compartilhada pelas homes de RH, TI e Financeiro (hero + grade de
 * atalhos) — a mídia do hero (SVG de ícone ou foto) é projetada via
 * `[hero-media]`, já que cada módulo usa algo diferente ali. */
@Component({
  selector: 'app-home-modulo',
  imports: [RouterLink],
  templateUrl: './home-modulo.html',
  styleUrl: './home-modulo.scss',
})
export class HomeModulo {
  private readonly sessao = inject(Sessao);
  private readonly sanitizer = inject(DomSanitizer);

  eyebrow = input.required<string>();
  titulo = input.required<string>();
  subtitulo = input.required<string>();
  atalhos = input.required<AtalhoModulo[]>();

  protected iconeSeguro(svg: string): SafeHtml {
    return this.sanitizer.bypassSecurityTrustHtml(svg);
  }

  protected ehVisivel(atalho: AtalhoModulo): boolean {
    return !atalho.somenteAdmin || this.sessao.administrador();
  }
}
