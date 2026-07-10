import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, input } from '@angular/core';

export interface Transacao {
  idTransacao: number;
  descricao: string;
  valor: number;
  dataTransacao: string | Date;
  tipoTransacao: 'ENTRADA' | 'SAIDA';
  statusTransacao: 'PAGO' | 'PENDENTE' | 'CANCELADO';
  conta?: { nomeConta: string } | null;
  categoria?: { nomeCategoria: string } | null;
  entidade?: { nome: string } | null;
}

@Component({
  selector: 'app-tabela-transacoes',
  imports: [DatePipe, CurrencyPipe],
  templateUrl: './tabela-transacoes.html',
  styleUrl: './tabela-transacoes.scss'
})
export class TabelaTransacoes {
  transacoes = input<Transacao[]>([]);

  protected readonly statusLabels: Record<Transacao['statusTransacao'], string> = {
    PAGO: 'Pago',
    PENDENTE: 'Pendente',
    CANCELADO: 'Cancelado'
  };
}