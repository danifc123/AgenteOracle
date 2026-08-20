import { Component, computed, signal } from '@angular/core';
import { Botao } from '../../../componentes/botao/botao';
import { CartaoKpi } from '../../../componentes/cartao-kpi/cartao-kpi';
import { EstadoVazio } from '../../../componentes/estado-vazio/estado-vazio';
import { ModuloHeader } from '../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../componentes/select-busca/select-busca';

interface Movimentacao {
  data: string;
  produto: string;
  tipo: 'entrada' | 'saida';
  quantidade: number;
  origemDestino: string;
  documento: string;
}

interface ItemSuprimento {
  produto: string;
  estoqueAtual: number;
  estoqueMinimo: number;
}

type StatusSuprimento = 'ok' | 'baixo' | 'critico';

const ROTULOS_STATUS: Record<StatusSuprimento, string> = {
  ok: 'OK',
  baixo: 'Baixo',
  critico: 'Crítico',
};

// Dados de mentira só pra construir/ajustar os componentes visuais — troca
// pra dados reais assim que existir a consulta SQL desse módulo (ainda não
// existe nenhuma view de estoque).
const MOCK_FILIAIS: OpcaoSelectBusca[] = [
  { valor: '0101', rotulo: '0101 - Matriz' },
  { valor: '0102', rotulo: '0102 - Filial Sul' },
];

const MOCK_MOVIMENTACOES: Movimentacao[] = [
  {
    data: '28/07/2026',
    produto: 'Semente de Soja RR',
    tipo: 'entrada',
    quantidade: 1200,
    origemDestino: 'Cooperativa Agrícola Central',
    documento: 'NF 45210',
  },
  {
    data: '27/07/2026',
    produto: 'Fertilizante NPK 20-05-20',
    tipo: 'saida',
    quantidade: 340,
    origemDestino: 'Fazenda Santa Rita',
    documento: 'REQ 8821',
  },
  {
    data: '26/07/2026',
    produto: 'Defensivo Agrícola Glifosato',
    tipo: 'entrada',
    quantidade: 500,
    origemDestino: 'Distribuidora AgroMax',
    documento: 'NF 45198',
  },
  {
    data: '25/07/2026',
    produto: 'Óleo Diesel S10',
    tipo: 'saida',
    quantidade: 2000,
    origemDestino: 'Frota Própria',
    documento: 'REQ 8815',
  },
  {
    data: '24/07/2026',
    produto: 'Semente de Milho Híbrido',
    tipo: 'saida',
    quantidade: 180,
    origemDestino: 'Fazenda Boa Vista',
    documento: 'REQ 8809',
  },
  {
    data: '23/07/2026',
    produto: 'Fertilizante NPK 20-05-20',
    tipo: 'entrada',
    quantidade: 800,
    origemDestino: 'Cooperativa Agrícola Central',
    documento: 'NF 45177',
  },
  {
    data: '22/07/2026',
    produto: 'Calcário Dolomítico',
    tipo: 'entrada',
    quantidade: 3000,
    origemDestino: 'Mineradora Rocha Forte',
    documento: 'NF 45160',
  },
  {
    data: '21/07/2026',
    produto: 'Defensivo Agrícola Glifosato',
    tipo: 'saida',
    quantidade: 120,
    origemDestino: 'Fazenda Santa Rita',
    documento: 'REQ 8790',
  },
];

const MOCK_SUPRIMENTOS: ItemSuprimento[] = [
  { produto: 'Semente de Soja RR', estoqueAtual: 4200, estoqueMinimo: 2000 },
  { produto: 'Fertilizante NPK 20-05-20', estoqueAtual: 1460, estoqueMinimo: 1500 },
  { produto: 'Defensivo Agrícola Glifosato', estoqueAtual: 380, estoqueMinimo: 1000 },
  { produto: 'Óleo Diesel S10', estoqueAtual: 5200, estoqueMinimo: 3000 },
  { produto: 'Semente de Milho Híbrido', estoqueAtual: 620, estoqueMinimo: 800 },
  { produto: 'Calcário Dolomítico', estoqueAtual: 8100, estoqueMinimo: 4000 },
];

@Component({
  selector: 'app-estoque',
  imports: [ModuloHeader, SelectBusca, Botao, CartaoKpi, EstadoVazio],
  templateUrl: './estoque.html',
  styleUrl: './estoque.scss',
})
export class Estoque {
  protected readonly filiais = signal<OpcaoSelectBusca[]>(MOCK_FILIAIS);
  protected readonly filiaisSelecionadas = signal<string[]>([]);

  protected readonly jaCarregou = signal(false);
  protected readonly movimentacoes = signal<Movimentacao[]>([]);
  protected readonly suprimentos = signal<ItemSuprimento[]>([]);

  protected readonly podeCarregar = computed(() => this.filiaisSelecionadas().length > 0);

  protected readonly totalEntradas = computed(() =>
    this.movimentacoes()
      .filter((item) => item.tipo === 'entrada')
      .reduce((soma, item) => soma + item.quantidade, 0),
  );
  protected readonly totalSaidas = computed(() =>
    this.movimentacoes()
      .filter((item) => item.tipo === 'saida')
      .reduce((soma, item) => soma + item.quantidade, 0),
  );
  protected readonly saldoPeriodo = computed(() => this.totalEntradas() - this.totalSaidas());
  protected readonly itensSuprimentoBaixo = computed(
    () => this.suprimentos().filter((item) => this.statusSuprimento(item) !== 'ok').length,
  );

  protected carregarEstoque(): void {
    if (!this.podeCarregar()) {
      return;
    }
    this.jaCarregou.set(true);
    this.movimentacoes.set(MOCK_MOVIMENTACOES);
    this.suprimentos.set(MOCK_SUPRIMENTOS);
  }

  protected rotuloStatus(status: StatusSuprimento): string {
    return ROTULOS_STATUS[status];
  }

  protected statusSuprimento(item: ItemSuprimento): StatusSuprimento {
    if (item.estoqueAtual <= item.estoqueMinimo * 0.5) {
      return 'critico';
    }
    if (item.estoqueAtual <= item.estoqueMinimo) {
      return 'baixo';
    }
    return 'ok';
  }
}
