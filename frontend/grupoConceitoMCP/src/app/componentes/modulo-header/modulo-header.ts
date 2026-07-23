import { Component, input } from '@angular/core';

@Component({
  selector: 'app-modulo-header',
  imports: [],
  templateUrl: './modulo-header.html',
  styleUrl: './modulo-header.scss'
})
export class ModuloHeader {
  breadcrumb = input.required<string>();
  titulo = input.required<string>();
  descricao = input<string>('');
}
