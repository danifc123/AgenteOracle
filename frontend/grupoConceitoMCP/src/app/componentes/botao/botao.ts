import { Component, input, output } from '@angular/core';

export type BotaoVariant = 'primaria' | 'acao' | 'perigo' | 'icone' | 'contorno' | 'enviar';

@Component({
  selector: 'app-botao',
  imports: [],
  templateUrl: './botao.html',
  styleUrl: './botao.scss'
})
export class Botao {
  variant = input<BotaoVariant>('primaria');
  type = input<'button' | 'submit'>('button');
  loading = input(false);
  loadingText = input('');
  disabled = input(false);
  pressed = input(false);
  ariaLabel = input<string | null>(null);
  title = input<string | null>(null);

  clicked = output<void>();
}
