import { ViewFinanceira } from '../../../../dadosRelatorios/views-financeiras';
import { filtrosPorColuna } from './filtros-relatorio';

const views: ViewFinanceira[] = [
  {
    nome: 'vw_clientes',
    descricao: '',
    relacionamentos: [],
    colunas: [
      { nome: 'nome', descricao: '', tipo: 'texto' },
      { nome: 'saldo', descricao: '', tipo: 'numero' },
      { nome: 'data_cadastro', descricao: '', tipo: 'periodo-data' },
    ],
  },
];

describe('filtrosPorColuna', () => {
  it('coluna texto: separa a string por vírgula em lista de valores', () => {
    const resultado = filtrosPorColuna(
      views,
      { vw_clientes: ['nome'] },
      { 'vw_clientes.nome': 'Ana,Bruno' },
    );
    expect(resultado).toEqual({ 'vw_clientes.nome': { valores: ['Ana', 'Bruno'] } });
  });

  it('coluna numero: usa min/max a partir de _ini/_fim', () => {
    const resultado = filtrosPorColuna(
      views,
      { vw_clientes: ['saldo'] },
      { 'vw_clientes.saldo_ini': '100', 'vw_clientes.saldo_fim': '500' },
    );
    expect(resultado).toEqual({ 'vw_clientes.saldo': { min: '100', max: '500' } });
  });

  it('coluna periodo-data: usa ini/fim a partir de _ini/_fim', () => {
    const resultado = filtrosPorColuna(
      views,
      { vw_clientes: ['data_cadastro'] },
      { 'vw_clientes.data_cadastro_ini': '2026-01-01' },
    );
    expect(resultado).toEqual({ 'vw_clientes.data_cadastro': { ini: '2026-01-01' } });
  });

  it('coluna sem valor preenchido não entra no resultado', () => {
    const resultado = filtrosPorColuna(views, { vw_clientes: ['nome', 'saldo'] }, {});
    expect(resultado).toEqual({});
  });
});
