import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-modulo-header',
  imports: [RouterLink],
  templateUrl: './modulo-header.html',
  styleUrl: './modulo-header.scss'
})
export class ModuloHeader {
  breadcrumb = input.required<string>();
  titulo = input.required<string>();
  descricao = input<string>('');
}
