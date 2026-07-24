import { Component, input, model } from '@angular/core';

export interface OpcaoCategoria {
  nome: string;
  cor: string;
}

@Component({
  selector: 'app-filtro-categorias',
  imports: [],
  templateUrl: './filtro-categorias.html',
  styleUrl: './filtro-categorias.scss'
})
export class FiltroCategorias {
  categorias = input.required<OpcaoCategoria[]>();

  /** null representa o chip "Todos". */
  selecionada = model<string | null>(null);

  protected selecionar(categoria: string | null): void {
    this.selecionada.set(categoria);
  }
}
