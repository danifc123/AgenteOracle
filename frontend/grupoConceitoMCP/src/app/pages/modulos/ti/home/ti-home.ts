import { Component } from '@angular/core';
import { AtalhoModulo, HomeModulo } from '../../../../componentes/home-modulo/home-modulo';

const ATALHOS: AtalhoModulo[] = [
  {
    titulo: 'Segurança de TI',
    texto:
      'A IA analisa padrão de login e volume de acesso a dado recente e aponta possível tentativa de invasão ou acesso suspeito.',
    rota: '/ti/seguranca',
    iconeSvg: `<path d="M12 3l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3Z" stroke-linecap="round" stroke-linejoin="round" /><path d="M12 8v5M12 16.5h.01" stroke-linecap="round" />`,
  },
  {
    titulo: 'Auditoria de Chamados',
    texto:
      'A IA audita cada chamado novo do GLPI e só libera pra fila de atendimento quando tem informação suficiente.',
    rota: '/ti/chamados',
    iconeSvg: `<path d="M4 5h16v11H8l-4 4V5Z" stroke-linecap="round" stroke-linejoin="round" /><path d="M8 10h8M8 13h5" stroke-linecap="round" />`,
  },
  {
    titulo: 'Central de suporte',
    texto: 'Encontrou um bug ou está com dificuldade? Abra um chamado no GLPI.',
    href: 'https://suporte.grupoconceito.com/front/central.php',
    iconeSvg: `<circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7v.3" stroke-linecap="round" stroke-linejoin="round" /><circle cx="12" cy="17" r="0.15" fill="currentColor" stroke-width="2.4" />`,
  },
];

/** Home do time de TI — mostrada em `/` pra quem só tem o módulo TI
 * liberado, e pra desenvolvedor quando troca pro TI no seletor do layout.
 * Casca (hero + atalhos) compartilhada com RH e Financeiro via
 * `app-home-modulo` — TI não tem foto ilustrativa (nenhuma disponível
 * ainda), usa o próprio ícone do grupo do menu (`itens-menu.ts`) ampliado
 * no lugar da imagem. */
@Component({
  selector: 'app-ti-home',
  imports: [HomeModulo],
  templateUrl: './ti-home.html',
  styleUrl: './ti-home.scss',
})
export class TiHome {
  protected readonly atalhos = ATALHOS;
}
