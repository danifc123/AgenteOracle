import { Component, inject } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';
import { Sessao } from '../../../../servicos/sessao';

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
  somenteAdmin?: boolean;
}

const ATALHOS: Atalho[] = [
  {
    titulo: 'Módulos financeiros',
    texto: 'Relatórios financeiros específicos do Grupo Conceito.',
    rota: '/financeiro/especifico-grupo-conceito',
    iconeSvg: `<rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18M8 6V4h8v2" stroke-linecap="round" />`,
  },
  {
    titulo: 'Criar relatório',
    texto: 'Monte seu próprio relatório escolhendo tabela, colunas e filtros.',
    rota: '/financeiro/criar-relatorio',
    iconeSvg: `<rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M9 10v10" stroke-linecap="round" />`,
  },
  {
    titulo: 'Assistente IA',
    texto: 'Peça relatórios em linguagem natural e baixe o resultado em Excel na hora.',
    rota: '/financeiro/chat',
    iconeSvg: `<path d="M4 5h16v11H8l-4 4V5Z" stroke-linecap="round" stroke-linejoin="round" />`,
  },
  {
    titulo: 'Histórico de relatórios',
    texto: 'Veja, baixe ou fixe relatórios já gerados pelo assistente.',
    rota: '/relatorios/historico',
    iconeSvg: `<path d="M12 8v4l3 3" stroke-linecap="round" stroke-linejoin="round" /><circle cx="12" cy="12" r="9" />`,
  },
  {
    titulo: 'Usuários',
    texto: 'Cadastre e gerencie os usuários com acesso ao sistema.',
    rota: '/usuarios',
    somenteAdmin: true,
    iconeSvg: `<circle cx="9" cy="8" r="3.2" /><path d="M3.5 19c0-3 2.5-5.2 5.5-5.2s5.5 2.2 5.5 5.2" stroke-linecap="round" /><path d="M16 9.5a2.7 2.7 0 1 0 0-5.4M18.5 19c0-2.4-1.7-4.4-4-5" stroke-linecap="round" />`,
  },
  {
    titulo: 'Central de suporte',
    texto: 'Encontrou um bug ou está com dificuldade? Abra um chamado com o time de TI.',
    href: 'https://suporte.grupoconceito.com/front/central.php',
    iconeSvg: `<circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7v.3" stroke-linecap="round" stroke-linejoin="round" /><circle cx="12" cy="17" r="0.15" fill="currentColor" stroke-width="2.4" />`,
  },
];

/** Home do time Financeiro — mostrada em `/` pra quem tem o módulo
 * Financeiro liberado (prioridade sobre os outros módulos em
 * `home-roteador.ts`), e pra desenvolvedor quando troca pro Financeiro no
 * seletor do layout. Mesmo padrão de `pages/modulos/rh/home/rh-home.ts` e
 * `pages/modulos/ti/home/ti-home.ts` (hero + atalhos) — esta é a original
 * de onde o padrão veio, com foto ilustrativa própria do time. */
@Component({
  selector: 'app-financeiro-home',
  imports: [RouterLink],
  templateUrl: './financeiro-home.html',
  styleUrl: './financeiro-home.scss',
})
export class FinanceiroHome {
  protected readonly sessao = inject(Sessao);
  protected readonly atalhos = ATALHOS;
  private readonly sanitizer = inject(DomSanitizer);

  protected iconeSeguro(svg: string): SafeHtml {
    return this.sanitizer.bypassSecurityTrustHtml(svg);
  }
}
