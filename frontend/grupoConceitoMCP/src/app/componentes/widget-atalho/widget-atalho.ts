import { Component, computed, inject, input } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';

/** Widget de navegação (card clicável) — reaproveitado por todo atalho de
 * todo módulo na Home única (ver `pages/home/catalogo-widgets-home.ts`).
 * Antes esses atalhos ficavam fixos numa seção separada da grade de
 * indicadores; agora são widget igual qualquer outro, que o usuário
 * escolhe incluir/remover/reordenar.
 *
 * Diferente dos widgets de indicador (`widget-chamados-total` e
 * companhia, que buscam o próprio dado), este NÃO busca nada — recebe
 * tudo pronto via `@Input` (`NgComponentOutletInputs`, ver `home.html`),
 * porque o mesmo componente é reaproveitado por todo atalho de todo
 * módulo, só variando o conteúdo estático. Um dos dois, `rota` (navegação
 * interna) ou `href` (link externo), precisa ser informado. */
@Component({
  selector: 'app-widget-atalho',
  imports: [RouterLink],
  templateUrl: './widget-atalho.html',
  styleUrl: './widget-atalho.scss',
})
export class WidgetAtalho {
  private readonly sanitizer = inject(DomSanitizer);

  titulo = input.required<string>();
  texto = input.required<string>();
  iconeSvg = input.required<string>();
  rota = input<string | null>(null);
  href = input<string | null>(null);

  protected readonly iconeSeguro = computed<SafeHtml>(() =>
    this.sanitizer.bypassSecurityTrustHtml(this.iconeSvg()),
  );
}
