import { Component, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { CoresAmbiente } from './servicos/cores-ambiente/cores-ambiente';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  // Só pra ativar o singleton cedo (raiz do app, sempre renderizada) — a
  // classe em si não expõe nada que este componente precise chamar, o
  // efeito dela é aplicar as cores salvas no <html> assim que loga, não só
  // quando a tela de Configurações é aberta (diferente de `CoresCategoria`,
  // que só importa dentro do módulo Financeiro).
  private readonly _coresAmbiente = inject(CoresAmbiente);

  protected readonly title = signal('Grupo Conceito');
}
