import { Component, input } from '@angular/core';

/** Pílula de status colorida (texto curto, tom semântico) — achado real do
 * audit de componentes: o mesmo padrão visual existia reinventado de forma
 * independente em pelo menos 9 páginas e 3 componentes compartilhados
 * (`saude-roster.scss` `.selo`, `detalhe-candidato.scss` `.badge-meta`,
 * `usuarios.scss` `.badge-ativo`, etc.), cada um com classe e cor
 * ligeiramente diferentes. Este componente é a primeira migração real
 * (`saude-roster`, que motivou este audit) — os outros ~9 pontos ficam
 * documentados como roteiro, não migrados junto.
 *
 * Usa os tokens semânticos de `styles.scss` (`--color-error`/`-warning`/
 * `-success`, cada um com par `-soft` pro fundo) — sem eles, cada `tom`
 * exigiria inventar hex de novo aqui.
 *
 * Ícone opcional via `<ng-content>` (SVG inline, mesmo padrão do resto do
 * projeto — não existe um componente `Icon` genérico, ver docstring de
 * `saude-roster.ts`); sem conteúdo projetado, só o texto aparece.
 *
 * Fora do escopo de propósito: `filtro-categorias.scss` `.chip` — é um
 * filtro clicável com estado ativo/inativo, categoria de componente
 * diferente (interativo, não só rótulo). */
@Component({
  selector: 'app-selo',
  imports: [],
  templateUrl: './selo.html',
  styleUrl: './selo.scss',
})
export class Selo {
  texto = input.required<string>();
  tom = input<'ok' | 'atencao' | 'erro' | 'neutro'>('neutro');
}
