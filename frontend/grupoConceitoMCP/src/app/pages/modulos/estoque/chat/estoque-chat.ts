import { Component } from '@angular/core';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';

@Component({
  selector: 'app-estoque-chat',
  imports: [ModuloHeader, EstadoVazio],
  templateUrl: './estoque-chat.html',
  styleUrl: './estoque-chat.scss',
})
export class EstoqueChat {}
