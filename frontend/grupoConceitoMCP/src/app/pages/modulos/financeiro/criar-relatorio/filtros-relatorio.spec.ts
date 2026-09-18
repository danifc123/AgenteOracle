import { ViewFinanceira } from '../../../../dadosRelatorios/views-financeiras/views-financeiras';
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
  {
    nome: 'vwia_notas_compra',
    descricao: '',
    relacionamentos: [],
    colunas: [{ nome: 'nota', descricao: '', tipo: 'texto-numerico' }],
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

  it('coluna texto-numerico: modo lista usa "valores", igual ao tipo texto', () => {
    const resultado = filtrosPorColuna(
      views,
      { vwia_notas_compra: ['nota'] },
      { 'vwia_notas_compra.nota': '000000002,000000499' },
    );
    expect(resultado).toEqual({
      'vwia_notas_compra.nota': { valores: ['000000002', '000000499'] },
    });
  });

  it('coluna texto-numerico: modo faixa usa min/max, igual ao tipo numero', () => {
    const resultado = filtrosPorColuna(
      views,
      { vwia_notas_compra: ['nota'] },
      { 'vwia_notas_compra.nota_ini': '2', 'vwia_notas_compra.nota_fim': '499' },
    );
    expect(resultado).toEqual({ 'vwia_notas_compra.nota': { min: '2', max: '499' } });
  });

  it('coluna texto-numerico: manda os dois filtros juntos se os dois estiverem preenchidos', () => {
    const resultado = filtrosPorColuna(
      views,
      { vwia_notas_compra: ['nota'] },
      {
        'vwia_notas_compra.nota': '000000002',
        'vwia_notas_compra.nota_ini': '2',
        'vwia_notas_compra.nota_fim': '499',
      },
    );
    expect(resultado).toEqual({
      'vwia_notas_compra.nota': { valores: ['000000002'], min: '2', max: '499' },
    });
  });
});
