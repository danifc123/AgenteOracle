import { Component, inject } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';

interface Atalho {
  titulo: string;
  texto: string;
  /** Conteúdo interno do `<svg>` (paths/rects/circles), como HTML puro —
   * confiável porque vem só deste arquivo estático, nunca de dado externo. */
  iconeSvg: string;
  /** Um dos dois deve ser informado: `rota` pra navegação interna
   * (`routerLink`), `href` pra link externo (abre em nova aba). */
  rota?: string;
  href?: string;
}

const ATALHOS: Atalho[] = [
  {
    titulo: 'Análise de Candidato',
    texto:
      'Suba currículos pro pool de candidatos ativos, ou descreva uma vaga pra IA buscar quem encaixa melhor.',
    rota: '/rh/analise-candidato',
    iconeSvg: `<path d="M9 12h6M9 16h6M9 8h2" stroke-linecap="round" /><path d="M7 3h7l4 4v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" stroke-linejoin="round" />`,
  },
  {
    titulo: 'Repescagem',
    texto:
      'Candidatos já dispensados — reconsidere pra uma vaga nova navegando na lista ou pedindo pra IA buscar entre eles.',
    rota: '/rh/repescagem',
    iconeSvg: `<path d="M4 4v6h6" stroke-linecap="round" stroke-linejoin="round" /><path d="M20 20v-6h-6" stroke-linecap="round" stroke-linejoin="round" /><path d="M5.5 15a7 7 0 0 0 12.3 2.5M18.5 9a7 7 0 0 0-12.3-2.5" stroke-linecap="round" />`,
  },
  {
    titulo: 'Colaboradores',
    texto:
      'Consulte o pool de candidatos já contratados, separado dos que ainda estão em avaliação.',
    rota: '/rh/colaboradores',
    iconeSvg: `<circle cx="9" cy="8" r="3.2" /><path d="M3.5 19c0-3 2.5-5.2 5.5-5.2s5.5 2.2 5.5 5.2" stroke-linecap="round" /><path d="m15 13 2 2 4-4" stroke-linecap="round" stroke-linejoin="round" />`,
  },
  {
    titulo: 'Central de suporte',
    texto: 'Encontrou um bug ou está com dificuldade? Abra um chamado com o time de TI.',
    href: 'https://suporte.grupoconceito.com/front/central.php',
    iconeSvg: `<circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7v.3" stroke-linecap="round" stroke-linejoin="round" /><circle cx="12" cy="17" r="0.15" fill="currentColor" stroke-width="2.4" />`,
  },
];

/** Home do time de RH — mostrada em `/` pra quem só tem o módulo RH
 * liberado, e pra desenvolvedor quando troca pro RH no seletor do layout.
 * Mesmo padrão de `pages/modulos/financeiro/home/financeiro-home.ts`
 * (hero + atalhos), sem foto ilustrativa (nenhuma disponível pra RH
 * ainda) — usa o próprio ícone do grupo do menu (`itens-menu.ts`)
 * ampliado no lugar da imagem. */
@Component({
  selector: 'app-rh-home',
  imports: [RouterLink],
  templateUrl: './rh-home.html',
  styleUrl: './rh-home.scss',
})
export class RhHome {
  protected readonly atalhos = ATALHOS;
  private readonly sanitizer = inject(DomSanitizer);

  protected iconeSeguro(svg: string): SafeHtml {
    return this.sanitizer.bypassSecurityTrustHtml(svg);
  }
}
