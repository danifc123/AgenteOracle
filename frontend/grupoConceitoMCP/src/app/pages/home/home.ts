import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Sessao } from '../../servicos/sessao';

@Component({
  selector: 'app-home',
  imports: [RouterLink],
  templateUrl: './home.html',
  styleUrl: './home.scss'
})
export class Home {
  protected readonly sessao = inject(Sessao);
}
