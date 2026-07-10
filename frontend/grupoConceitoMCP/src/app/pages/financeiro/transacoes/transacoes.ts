import { Component } from '@angular/core';
import { TabelaTransacoes, Transacao } from '../../../componentes/tabela-transacoes/tabela-transacoes';

@Component({
  selector: 'app-transacoes',
  imports: [TabelaTransacoes],
  templateUrl: './transacoes.html',
  styleUrl: './transacoes.scss'
})
export class Transacoes {
  transacoes: Transacao[] = [];
}
