import { Component, input, model } from '@angular/core';

@Component({
  selector: 'app-busca',
  imports: [],
  templateUrl: './busca.html',
  styleUrl: './busca.scss'
})
export class Busca {
  placeholder = input('Buscar...');
  valor = model('');

  limpar(): void {
    this.valor.set('');
  }
}
