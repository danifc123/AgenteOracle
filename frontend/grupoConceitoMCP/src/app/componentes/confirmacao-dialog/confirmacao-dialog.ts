import { Component, input, output } from '@angular/core';
import { Botao } from '../botao/botao';
import { Dialog } from '../dialog/dialog';

@Component({
  selector: 'app-confirmacao-dialog',
  imports: [Dialog, Botao],
  templateUrl: './confirmacao-dialog.html',
  styleUrl: './confirmacao-dialog.scss',
})
export class ConfirmacaoDialog {
  aberto = input(false);
  titulo = input('Confirmar ação');
  mensagem = input('');
  confirmando = input(false);
  textoConfirmar = input('Apagar');
  textoConfirmando = input('Apagando...');

  confirmar = output<void>();
  cancelar = output<void>();
}
