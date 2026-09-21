import { Component, computed, input, output } from '@angular/core';

let proximoId = 0;

/** Campo de número curto com sufixo, ajuda e erro; devolve texto, quem usa valida. */
@Component({
  selector: 'app-campo-numerico',
  imports: [],
  templateUrl: './campo-numerico.html',
  styleUrl: './campo-numerico.scss',
})
export class CampoNumerico {
  rotulo = input.required<string>();
  valor = input('');
  sufixo = input('');
  descricao = input('');
  erro = input<string | null>(null);
  desabilitado = input(false);

  valorChange = output<string>();

  protected readonly id = `campo-numerico-${proximoId++}`;

  protected readonly idsDescricao = computed(() => {
    const ids = [
      this.descricao() ? `${this.id}-descricao` : null,
      this.erro() ? `${this.id}-erro` : null,
    ];
    return ids.filter(Boolean).join(' ') || null;
  });

  protected aoDigitar(evento: Event): void {
    this.valorChange.emit((evento.target as HTMLInputElement).value);
  }
}
